from typing import Any, Dict, List
from openai import OpenAI


def build_client(
    model_name: str,
    api_key: str,
    base_url: str,
    timeout: float = 600.0,
):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )

    return client

def generate_response(
    client: Any,
    messages: List[Dict[str, str]],
    model: str = "deepseek-v3.2",  
    temperature: float = 1.0,
    max_tokens: int = 8192,
    tools=None,
    enable_thinking: bool = False,
    **kwargs
):
    """Generate response from LLM client"""
    if enable_thinking:
        if 'dashscope' in str(client._base_url).lower():
            extra_body = {'enable_thinking': True}
        else:
            extra_body = {'thinking': {"type": "enabled"}}
    else:
        extra_body = {"thinking": {"type": "disabled"}}
        
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        extra_body=extra_body,
        **kwargs
    )
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    messages = response.choices[0].message
    return messages, input_tokens, output_tokens
