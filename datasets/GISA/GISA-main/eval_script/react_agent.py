import os
import re
from tqdm import tqdm  
import json
import json_repair
from dotenv import load_dotenv 
from typing import List, Dict, Any, Optional
# from datetime import datetime
import datetime
import time

from tools import Search, Visit
from prompts import FC_REACT_AGENT_PROMPT, TOOLS_DEFINITION
from utils import build_client, generate_response

class ReActAgent:
    def __init__(
        self,
        model_name: str,
        api_base_url: str,
        api_key: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        max_running_steps: int = 30,
        enable_thinking: bool = True
    ):
        self.model_name = model_name
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking
        self.max_running_steps = max_running_steps

        self.current_date = str(datetime.date.today().strftime("%Y-%m-%d"))
        self.tools = {"search": Search(), "visit": Visit()} 
        self.is_openrouter = 'openrouter' in self.api_base_url.lower()


    def solve(self, question: str):
        messages = [
            {
                "role": "user", 
                "content": FC_REACT_AGENT_PROMPT.format(
                    question=question, 
                    current_date=self.current_date
                )
            }
        ]

        token_stats = {
            "total_input_tokens": 0, 
            "total_output_tokens": 0, 
            'tool_input_token_list': [],
            'tool_output_token_list': [],
            'tool_input_tokens': 0,
            'tool_output_tokens': 0
        }
        current_step = 0
        prediction = "No answer found"
        termination = "max_steps"

        while current_step < self.max_running_steps:
            print(f"Step {current_step} of {self.max_running_steps}")
            current_step += 1
            message, i_tok, o_tok = self._call_llm(
                messages, 
                tools=TOOLS_DEFINITION, 
                enable_thinking=self.enable_thinking
            )
            base_content = message.content
            tool_calls = message.tool_calls

            step_message = {
                "role": "assistant",
                "tool_calls": tool_calls,
                "content": base_content,
            }

            if self.enable_thinking:
                if self.is_openrouter:
                    step_message['reasoning_details'] = message.reasoning_details
                else:
                    step_message['reasoning_content'] = message.reasoning_content
            messages.append(step_message)

            token_stats["total_input_tokens"] += i_tok
            token_stats["total_output_tokens"] += o_tok

            if tool_calls:
                for tool in tool_calls:
                    if (self.max_running_steps - current_step) <= 1:
                        tool = tool_calls[0]
                        result = 'Sorry, the number of llm calls exceeds the limit. You have no chance to call tools. Please directly give the final answer.'
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool.id,
                            "content": result
                        })
                        continue
                    try:
                        tool_name = tool.function.name
                        tool_args = tool.function.arguments
                        tool_args = json_repair.loads(tool_args)
                        result, input_tokens, output_tokens = self.tools[tool_name].call(tool_args)

                        token_stats['total_input_tokens'] += input_tokens
                        token_stats['total_output_tokens'] += output_tokens
                        token_stats['tool_input_tokens'] += input_tokens
                        token_stats['tool_output_tokens'] += output_tokens
                        token_stats['tool_input_token_list'].append(input_tokens)
                        token_stats['tool_output_token_list'].append(output_tokens)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool.id,
                            "content": result
                        })
                    except Exception as e:
                        print(e)
                        print("current tool:", tool_name, tool_args)
                        result = 'Error: Tool call is not a valid JSON. Tool call must contain a valid "name" and "arguments" field.'
                        tool = tool_calls[0]
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool.id,
                            "content": result
                        })
            else:
                termination = 'answer'
                prediction = base_content
                break
        
        cleaned_messages = self.get_clean_messages(messages)

        return {
            "question": question,
            "prediction": prediction,
            "messages": cleaned_messages,
            "steps_taken": current_step,
            "termination_reason": termination,
            "token_stats": token_stats
        }
    

    def get_clean_messages(self,messages):
        final_messages = []
        for message in messages:
            clean_msg = message.copy()
            if "tool_calls" in clean_msg and clean_msg["tool_calls"]:
                clean_msg["tool_calls"] = [
                    {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                        "id": getattr(tool_call, 'id', None) 
                    }
                    for tool_call in clean_msg["tool_calls"]
                ]
            
            for k in list(clean_msg.keys()):
                v = clean_msg[k]
                if not isinstance(v, (str, int, float, list, dict, bool, type(None))):
                    del clean_msg[k]

            final_messages.append(clean_msg)
        return final_messages

    def _call_llm(self, msgs, tools=None, enable_thinking=False, max_tries=5):
        client = build_client(model_name=self.model_name, api_key=self.api_key, base_url=self.api_base_url)
        base_sleep_time = 1 
        for attempt in range(max_tries):
            basic_kwargs = {
                'client': client,
                'messages': msgs,
                'model': self.model_name,
                'max_tokens': self.max_tokens,
                'temperature': self.temperature,
                'tools': tools,
                'enable_thinking': enable_thinking,
            }
            if 'kimi' in self.model_name.lower():
                basic_kwargs['presence_penalty'] = 0.0
                basic_kwargs['temperature'] = 1.0
            elif 'gpt' in self.model_name.lower():
                basic_kwargs['parallel_tool_calls'] = False
            
            try:
                messages, input_tokens, output_tokens = generate_response(**basic_kwargs)
                return messages, input_tokens, output_tokens
            except Exception as e:
                print(f"Error: Attempt {attempt + 1} failed: {e}")

            if attempt < max_tries - 1:
                time.sleep(min(base_sleep_time * (2 ** attempt), 30))
        
        raise Exception("LLM server error!")

    def _save_log(self, data: Dict, output_dir: str, idx: int):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        filename = f"{output_dir}/{idx}.json" 
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def run(self, question_item: dict, output_dir: str):
        idx = question_item['id']
        filename = f"{output_dir}/{idx}.json"
        if os.path.exists(filename):
            return json.load(open(filename, 'r', encoding='utf-8'))

        start_time = time.time()
        
        result_data = self.solve(question_item['question'])
        
        total_time = time.time() - start_time
        result_data["idx"] = idx
        result_data['question_item'] = question_item
        result_data["total_time_seconds"] = total_time
        result_data["agent_type"] = self.__class__.__name__
        result_data["model_name"] = self.model_name

        self._save_log(result_data, output_dir, idx)
        return result_data
