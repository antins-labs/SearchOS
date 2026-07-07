import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor
import requests
import asyncio
import uuid
import http.client
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union
import requests
from openai import OpenAI
import random
from urllib.parse import urlparse, unquote
import time 
import tiktoken
from utils import build_client, generate_response
from prompts import EXTRACTOR_PROMPT 
from dotenv import load_dotenv
import io
import sys
import sqlite3
import threading
import hashlib
import re
import json_repair


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

JINA_API_KEYS = os.getenv("JINA_API_KEY", "")
SERPER_KEY = os.getenv('SERPER_API_KEY', "")
SUMMARY_API_KEY = os.getenv('SUMMARY_API_KEY', "")
SUMMARY_API_BASE_URL = os.getenv('SUMMARY_API_BASE_URL', "")
SUMMARY_MODEL_NAME = os.getenv('SUMMARY_MODEL_NAME', "")


class ToolCache:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path="tool_cache.db"):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ToolCache, cls).__new__(cls)
                    cls._instance.db_path = db_path
                    cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def get(self, key: str) -> Optional[str]:
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.execute("SELECT value FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            print(f"[Cache Read Error] {e}")
            return None

    def set(self, key: str, value: str):
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                    conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value))
                    conn.commit()
            except Exception as e:
                print(f"[Cache Write Error] {e}")


class BaseTool(ABC):
    name: str = ''
    description: str = ''
    parameters: Union[List[dict], dict] = []

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or {}
        if not self.name:
            raise ValueError(
                f'You must set {self.__class__.__name__}.name, either by @register_tool(name=...) or explicitly setting {self.__class__.__name__}.name'
            )
        

    @abstractmethod
    def call(self, params: Union[str, dict], **kwargs) -> Union[str, list, dict, List]:
        """The interface for calling tools.

        Each tool needs to implement this function, which is the workflow of the tool.

        Args:
            params: The parameters of func_call.
            kwargs: Additional parameters for calling tools.

        Returns:
            The result returned by the tool, implemented in the subclass.
        """
        raise NotImplementedError

    def _verify_json_format_args(self, params: Union[str, dict], strict_json: bool = False) -> dict:
        """Verify the parameters of the function call"""
        if isinstance(params, str):
            try:
                if strict_json:
                    params_json: dict = json.loads(params)
                else:
                    params_json: dict = json_repair.loads(params)
            except json.decoder.JSONDecodeError:
                raise ValueError('Parameters must be formatted as a valid JSON!')
        else:
            params_json: dict = params
        if isinstance(self.parameters, list):
            for param in self.parameters:
                if 'required' in param and param['required']:
                    if param['name'] not in params_json:
                        raise ValueError('Parameters %s is required!' % param['name'])
        elif isinstance(self.parameters, dict):
            import jsonschema
            jsonschema.validate(instance=params_json, schema=self.parameters)
        else:
            raise ValueError
        return params_json

    @property
    def function(self) -> dict:  # Bad naming. It should be `function_info`.
        return {
            'name_for_human': self.name_for_human,
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
            'args_format': self.args_format
        }

    @property
    def name_for_human(self) -> str:
        return self.cfg.get('name_for_human', self.name)

    @property
    def args_format(self) -> str:
        fmt = self.cfg.get('args_format')
        if fmt is None:
            if has_chinese_chars([self.name_for_human, self.name, self.description, self.parameters]):
                fmt = '此工具的输入应为JSON对象。'
            else:
                fmt = 'Format the arguments as a JSON object.'
        return fmt

    @property
    def file_access(self) -> bool:
        return False


class Search(BaseTool):
    name = "search"
    description = "Performs batched web searches: supply an array 'query'; the tool retrieves the top 10 results for each query in one call."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "Array of query strings. Include multiple complementary search queries in a single call."
            },
        },
        "required": ["query"],
    }
    def __init__(self, cfg: Optional[dict] = None):
        super().__init__(cfg)
        self.api_key = SERPER_KEY
        self.cache = ToolCache()  

    def google_search_with_serp(self, query: str):
        cache_key = f"search_v1:{query.strip()}"
        
        cached_result = self.cache.get(cache_key)
        if cached_result:
            print(f"[Search] Cache hit for: {query[:20]}...")
            return cached_result

        def contains_chinese_basic(text: str) -> bool:
            return any('\u4E00' <= char <= '\u9FFF' for char in text)

        url = "https://google.serper.dev/search"
        
        payload_dict = {"q": query}
        if contains_chinese_basic(query):
            payload_dict.update({"location": "China", "gl": "cn", "hl": "zh-cn"})
        else:
            payload_dict.update({"location": "United States", "gl": "us", "hl": "en"})

        headers = {
            'X-API-KEY': self.api_key, 
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, headers=headers, json=payload_dict, timeout=(3, 10))
            response.raise_for_status() 
            results = response.json()
        except Exception as e:
            print(f"Error searching for '{query}': {e}")
            return f"Google search failed for '{query}'. Error: {e}"

        try:
            if "organic" not in results:
                return f"No organic results found for query: '{query}'."

            web_snippets = []
            idx = 0
            for page in results["organic"]:
                idx += 1
                date_published = f"\nDate published: {page['date']}" if "date" in page else ""
                source = f"\nSource: {page['source']}" if "source" in page else ""
                snippet = f"\n{page['snippet']}" if "snippet" in page else ""
                
                link = page.get('link', '')
                title = page.get('title', 'No Title')

                redacted_version = f"{idx}. [{title}]({link}){date_published}{source}\n{snippet}"
                redacted_version = redacted_version.replace("Your browser can't play this video.", "")
                web_snippets.append(redacted_version)

            content = f"A Google search for '{query}' found {len(web_snippets)} results:\n\n## Web Results\n" + "\n\n".join(web_snippets)

            self.cache.set(cache_key, content)
            return content
        except Exception as e:
            return f"Error parsing results for '{query}'. {e}"

    def call(self, params: Union[str, dict], **kwargs) -> str:
        query = None
        if isinstance(params, str):
            try:
                params = json.loads(params)
                query = params.get("query")
            except:
                query = params
        elif isinstance(params, dict):
            query = params.get("query")

        if not query:
            return "[Search] Invalid request: 'query' is missing."

        if isinstance(query, str):
            queries = [query]
        elif isinstance(query, list):
            queries = query
        else:
            return "[Search] Invalid query format."

        results_map = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {executor.submit(self.google_search_with_serp, q): q for q in queries}
            
            for future in as_completed(future_to_query):
                original_q = future_to_query[future]
                try:
                    data = future.result()
                    results_map[original_q] = data
                except Exception as exc:
                    results_map[original_q] = f"Search generated an exception: {exc}"

        final_responses = []
        for q in queries:
            final_responses.append(results_map.get(q, "Error retrieval"))

        return "\n=======\n".join(final_responses), 0, 0


@staticmethod
def truncate_to_tokens(text: str, max_tokens: int = 95000) -> str:
    encoding = tiktoken.get_encoding("cl100k_base")
    
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    
    truncated_tokens = tokens[:max_tokens]
    return encoding.decode(truncated_tokens)


class Visit(BaseTool):
    name = 'visit'
    description = 'Visit webpage(s) and return the summary of the content.'
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": ["string", "array"],
                "items": {
                    "type": "string"
                    },
                "minItems": 1,
                "description": "The URL(s) of the webpage(s) to visit. Can be a single URL or an array of URLs."
        },
        "goal": {
                "type": "string",
                "description": "The goal of the visit for webpage(s)."
        }
        },
        "required": ["url", "goal"]
    }

    def __init__(self, cfg: Optional[dict] = None):
        super().__init__(cfg)
        self.cache = ToolCache() 

    def call(self, params: Union[str, dict], **kwargs) -> str:
        try:
            url = params["url"]
            goal = params["goal"]
        except:
            return "[Visit] Invalid request format: Input must be a JSON object containing 'url' and 'goal' fields"

        start_time = time.time()
        
        total_input_tokens = 0
        total_output_tokens = 0

        if isinstance(url, str):
            response, input_tokens, output_tokens = self.readpage_jina(url, goal)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
        else:
            response = []
            assert isinstance(url, List)
            start_time = time.time()
            for u in url: 
                if time.time() - start_time > 900:
                    cur_response = "The useful information in {url} for user goal {goal} as follows: \n\n".format(url=url, goal=goal)
                    cur_response += "Evidence in page: \n" + "The provided webpage content could not be accessed. Please check the URL or file format." + "\n\n"
                    cur_response += "Summary: \n" + "The webpage content could not be processed, and therefore, no information is available." + "\n\n"
                else:
                    try:
                        cur_response, input_tokens, output_tokens = self.readpage_jina(u, goal)
                        total_input_tokens += input_tokens
                        total_output_tokens += output_tokens
                    except Exception as e:
                        cur_response = f"Error fetching {u}: {str(e)}"
                response.append(cur_response)
            response = "\n=======\n".join(response)
        
        print(f'Summary Length {len(response)}; Summary Content {response}')
        return response.strip(), total_input_tokens, total_output_tokens

    def _extract_json(self, text: str) -> dict:
        if not text:
            raise ValueError("Empty content")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        clean_text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        clean_text = re.sub(r'^```\s*', '', clean_text, flags=re.MULTILINE)
        clean_text = clean_text.strip()
        
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            pass

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and start < end:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        raise ValueError("Could not extract valid JSON from response")
        
    def call_server(self, msgs, max_retries=2):
        api_key = SUMMARY_API_KEY
        url_llm = SUMMARY_API_BASE_URL
        model_name = SUMMARY_MODEL_NAME
        client = build_client(
            model_name=model_name,
            api_key=api_key,
            base_url=url_llm
        )
        for attempt in range(max_retries):
            try:
                messages, input_tokens, output_tokens = generate_response(
                    client=client,
                    messages=msgs,
                    model=model_name,
                    temperature=0.7,
                    max_tokens=8192,
                    tools=None,
                    enable_thinking=False
                )
                content = messages.content
                return content, input_tokens, output_tokens
            except Exception as e:
                print(e)
                if attempt == (max_retries - 1):
                    return "", 0, 0
                continue


    def jina_readpage(self, url: str) -> str:
        max_retries = 3
        timeout = 50
        
        for attempt in range(max_retries):
            headers = {
                "Authorization": f"Bearer {JINA_API_KEYS}",
            }
            try:
                response = requests.get(
                    f"https://r.jina.ai/{url}",
                    headers=headers,
                    timeout=timeout
                )
                if response.status_code == 200:
                    webpage_content = response.text
                    return webpage_content
                else:
                    print(response.text)
                    raise ValueError("jina readpage error")
            except Exception as e:
                time.sleep(0.5)
                if attempt == max_retries - 1:
                    return "[visit] Failed to read page."
                
        return "[visit] Failed to read page."

    def html_readpage_jina(self, url: str) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            content = self.jina_readpage(url)
            service = "jina"     
            if content and not content.startswith("[visit] Failed to read page.") and content != "[visit] Empty content." and not content.startswith("[document_parser]"):
                return content
        return "[visit] Failed to read page."

    def readpage_jina(self, url: str, goal: str) -> str:
        cache_key = f'visit_v1:{url}'

        cached_result = self.cache.get(cache_key)
        if cached_result:
            print(f"[Visit] Cache hit for URL: {url}")
            content = cached_result
        else:
            content = self.html_readpage_jina(url)
            self.cache.set(cache_key, content)
   
        summary_page_func = self.call_server
        max_retries = int(os.getenv('VISIT_SERVER_MAX_RETRIES', 1))

        total_input_tokens = 0
        total_output_tokens = 0

        if content and not content.startswith("[visit] Failed to read page.") and content != "[visit] Empty content." and not content.startswith("[document_parser]"):
            content = truncate_to_tokens(content, max_tokens=95000)
            messages = [{"role":"user","content": EXTRACTOR_PROMPT.format(webpage_content=content, goal=goal)}]
            parse_retry_times = 0
            raw, input_tokens, output_tokens = summary_page_func(messages, max_retries=max_retries)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            summary_retries = 3
            while len(raw) < 10 and summary_retries >= 0:
                truncate_length = int(0.7 * len(content)) if summary_retries > 0 else 25000
                status_msg = (
                    f"[visit] Summary url[{url}] " 
                    f"attempt {3 - summary_retries + 1}/3, "
                    f"content length: {len(content)}, "
                    f"truncating to {truncate_length} chars"
                ) if summary_retries > 0 else (
                    f"[visit] Summary url[{url}] failed after 3 attempts, "
                    f"final truncation to 25000 chars"
                )
                print(status_msg)
                content = content[:truncate_length]
                extraction_prompt = EXTRACTOR_PROMPT.format(
                    webpage_content=content,
                    goal=goal
                )
                messages = [{"role": "user", "content": extraction_prompt}]
                raw, input_tokens, output_tokens = summary_page_func(messages, max_retries=max_retries)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                summary_retries -= 1

            parse_retry_times = 0
            if isinstance(raw, str):
                raw = raw.replace("```json", "").replace("```", "").strip()
            while parse_retry_times < 3:
                try:
                    raw = json.loads(raw)
                    break
                except:
                    print("have error in readpage jina")
                    raw, input_tokens, output_tokens = summary_page_func(messages, max_retries=max_retries)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    parse_retry_times += 1
            
            if parse_retry_times >= 3:
                useful_information = "The useful information in {url} for user goal {goal} as follows: \n\n".format(url=url, goal=goal)
                useful_information += "Evidence in page: \n" + "The provided webpage content could not be accessed. Please check the URL or file format." + "\n\n"
                useful_information += "Summary: \n" + "The webpage content could not be processed, and therefore, no information is available." + "\n\n"
            else:
                useful_information = "The useful information in {url} for user goal {goal} as follows: \n\n".format(url=url, goal=goal)
                useful_information += "Evidence in page: \n" + str(raw["evidence"]) + "\n\n"
                useful_information += "Summary: \n" + str(raw["summary"]) + "\n\n"

            if len(useful_information) < 10 and summary_retries < 0:
                print("[visit] Could not generate valid summary after maximum retries")
                useful_information = "[visit] Failed to read page"
            
            return useful_information, total_input_tokens, total_output_tokens

        else:
            useful_information = "The useful information in {url} for user goal {goal} as follows: \n\n".format(url=url, goal=goal)
            useful_information += "Evidence in page: \n" + "The provided webpage content could not be accessed. Please check the URL or file format." + "\n\n"
            useful_information += "Summary: \n" + "The webpage content could not be processed, and therefore, no information is available." + "\n\n"
            return useful_information, total_input_tokens, total_output_tokens

