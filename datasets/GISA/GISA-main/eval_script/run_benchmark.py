import json
import json5
import os
from dotenv import load_dotenv
import time
import random
import datetime
import tiktoken
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm   
from typing import List, Dict, Any, Optional
import argparse

from react_agent import ReActAgent


def process_query(
    question_item, 
    output_dir, 
    api_key, 
    base_url, 
    model_name,
    enable_thinking=True
):
    agent = ReActAgent(api_key=api_key, api_base_url=base_url, model_name=model_name, enable_thinking=enable_thinking)
    return agent.run(question_item=question_item, output_dir=output_dir)

def load_benchmark_data(benchmark_data_path):
    with open(benchmark_data_path, 'r', encoding='utf-8') as f:
        data = [json.loads(line) for line in f.readlines()]
    return data

def run_benchmark(
    max_workers=5, 
    output_dir=None, 
    api_key=None,
    base_url=None,
    model_name=None,
    enable_thinking=True,
    save_note="",
    benchmark_data_path="./bench_data/question.jsonl"
):
    if save_note != "":
        save_note = f"_{save_note}"
    output_dir = os.path.join(output_dir, f"{model_name}_{'thinking' if enable_thinking else 'nothinking'}{save_note}")
    os.makedirs(output_dir, exist_ok=True)
    data = load_benchmark_data(benchmark_data_path)

    print(f"Starting Benchmark: Total=[{len(data)}] | Dir=[{output_dir}]")
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_query, q, output_dir, api_key, base_url, model_name, enable_thinking): q['id'] 
            for i, q in enumerate(data)
        }

        for future in tqdm(as_completed(future_to_idx), total=len(data)):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Error: {e}")

    results.sort(key=lambda x: x['idx'])
    with open(f"{output_dir}/_report_all.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    
    print(f"\nBenchmark Finished. Results saved to {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_workers", type=int, default=5)
    parser.add_argument("--api_key", type=str)
    parser.add_argument("--base_url", type=str)
    parser.add_argument("--model_name", type=str, default="qwen")
    parser.add_argument("--enable_thinking", type=bool, default=True)
    parser.add_argument("--save_note", type=str, default="")
    
    parser.add_argument("--output_dir", type=str, default="./benchmark_results")
    parser.add_argument("--benchmark_data_path", type=str, default="./bench_data/question.jsonl")
    args = parser.parse_args()
    
    run_benchmark(
        max_workers=args.num_workers, 
        output_dir=args.output_dir, 
        api_key=args.api_key, 
        base_url=args.base_url, 
        model_name=args.model_name, 
        enable_thinking=args.enable_thinking,
        save_note=args.save_note, 
        benchmark_data_path=args.benchmark_data_path
    )