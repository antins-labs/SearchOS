#!/usr/bin/env python3
"""
将未处理的数据集统一转换为 JSONL 格式，并完成解码/解密。
支持：
  1. browsecomp_zh/test.parquet  → browsecomp_zh/test.jsonl  (解密 + 转JSONL)
  2. frames/test.tsv             → frames/test.jsonl          (TSV → JSONL)
  3. GISA/encrypted_question.jsonl + answer/*.csv + trace/*.json → GISA/gisa.jsonl (解密 + 合并)
"""

import json
import csv
import base64
import hashlib
import os
import ast

import pandas as pd

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")


# ============ browsecomp_zh 解密逻辑 ============

def derive_key(password: str, length: int) -> bytes:
    hasher = hashlib.sha256()
    hasher.update(password.encode())
    key = hasher.digest()
    return key * (length // len(key)) + key[: length % len(key)]


def decrypt(ciphertext_b64: str, password: str) -> str:
    if not ciphertext_b64 or not password:
        return ciphertext_b64
    try:
        encrypted = base64.b64decode(ciphertext_b64)
        key = derive_key(password, len(encrypted))
        decrypted = bytes(a ^ b for a, b in zip(encrypted, key))
        return decrypted.decode("utf-8")
    except Exception as e:
        print(f"  [Warning] 解密失败: {e}")
        return ciphertext_b64


def process_browsecomp_zh():
    """解密 browsecomp_zh parquet 并输出 JSONL"""
    input_path = os.path.join(DATASETS_DIR, "browsecomp_zh", "test.parquet")
    output_path = os.path.join(DATASETS_DIR, "browsecomp_zh", "test.jsonl")

    if not os.path.exists(input_path):
        print(f"[跳过] 文件不存在: {input_path}")
        return

    print(f"处理 browsecomp_zh: {input_path}")
    df = pd.read_parquet(input_path)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            password = row["canary"]
            record = {
                "topic": decrypt(row["Topic"], password),
                "question": decrypt(row["Question"], password),
                "answer": decrypt(row["Answer"], password),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    print(f"  -> 已生成 {count} 条记录: {output_path}")


# ============ frames TSV 转换逻辑 ============

def process_frames():
    """将 frames TSV 转换为 JSONL"""
    input_path = os.path.join(DATASETS_DIR, "frames", "test.tsv")
    output_path = os.path.join(DATASETS_DIR, "frames", "test.jsonl")

    if not os.path.exists(input_path):
        print(f"[跳过] 文件不存在: {input_path}")
        return

    print(f"处理 frames: {input_path}")
    count = 0

    with open(input_path, "r", encoding="utf-8") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        reader = csv.DictReader(infile, delimiter="\t")
        for row in reader:
            # 收集非空的 wikipedia 链接
            wiki_links = []
            for i in range(1, 11):
                link = row.get(f"wikipedia_link_{i}", "")
                if link:
                    wiki_links.append(link)
            extra = row.get("wikipedia_link_11+", "")
            if extra:
                wiki_links.append(extra)

            # 尝试解析 wiki_links 列（Python list 字符串）
            raw_wiki_links = row.get("wiki_links", "")
            if raw_wiki_links:
                try:
                    parsed = ast.literal_eval(raw_wiki_links)
                    if isinstance(parsed, list) and len(parsed) > len(wiki_links):
                        wiki_links = parsed
                except (ValueError, SyntaxError):
                    pass

            record = {
                "question": row.get("Prompt", ""),
                "answer": row.get("Answer", ""),
                "reasoning_types": row.get("reasoning_types", ""),
                "wiki_links": wiki_links,
            }
            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    print(f"  -> 已生成 {count} 条记录: {output_path}")


# ============ GISA 解密 + 合并逻辑 ============

def process_gisa():
    """解密 GISA 问题，合并答案 CSV 和搜索轨迹，输出 JSONL"""
    gisa_dir = os.path.join(DATASETS_DIR, "GISA")
    question_path = os.path.join(gisa_dir, "encrypted_question.jsonl")
    answer_dir = os.path.join(gisa_dir, "answer")
    trace_dir = os.path.join(gisa_dir, "trace")
    output_path = os.path.join(gisa_dir, "gisa.jsonl")

    if not os.path.exists(question_path):
        print(f"[跳过] 文件不存在: {question_path}")
        return

    print(f"处理 GISA: {question_path}")
    count = 0

    with open(question_path, "r", encoding="utf-8") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        for line in infile:
            obj = json.loads(line.strip())
            qid = obj["id"]

            # 解密问题
            question = decrypt(str(obj["question"]), str(obj["canary"]))

            # 读取答案 CSV（部分文件非 UTF-8，用 latin-1 回退）
            answer_path = os.path.join(answer_dir, f"{qid}.csv")
            answer_data = []
            if os.path.exists(answer_path):
                for enc in ("utf-8-sig", "latin-1"):
                    try:
                        with open(answer_path, "r", encoding=enc) as af:
                            reader = csv.DictReader(af)
                            answer_data = [dict(row) for row in reader]
                        break
                    except UnicodeDecodeError:
                        continue

            # 读取搜索轨迹
            trace_path = os.path.join(trace_dir, f"{qid}.json")
            trace_data = None
            if os.path.exists(trace_path):
                with open(trace_path, "r", encoding="utf-8") as tf:
                    trace_data = json.load(tf)

            record = {
                "id": qid,
                "question": question,
                "answer_type": obj.get("answer_type", ""),
                "question_type": obj.get("question_type", ""),
                "topic": obj.get("topic", ""),
                "answer": answer_data,
                "trace": trace_data,
            }
            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    print(f"  -> 已生成 {count} 条记录: {output_path}")


# ============ 主函数 ============

if __name__ == "__main__":
    print("=" * 50)
    print("数据集处理：转换为 JSONL + 解密")
    print("=" * 50)
    process_browsecomp_zh()
    print()
    process_frames()
    print()
    process_gisa()
    print()
    print("全部完成！")
