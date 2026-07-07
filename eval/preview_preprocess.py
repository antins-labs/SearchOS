"""Dry-run preprocess on first N benchmark questions; print before/after."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env():
    for cand in [Path.cwd() / ".env", Path(__file__).parent.parent / ".env"]:
        if cand.exists():
            load_dotenv(cand)
            return


async def _amain(args):
    if args.benchmark == "widesearch":
        from eval.benchmarks.widesearch import load_samples
        data = "datasets/widesearch/widesearch.jsonl"
        gold = "datasets/widesearch/widesearch_gold"
    else:
        from eval.benchmarks.gisa import load_samples
        data = "datasets/GISA/gisa_100.jsonl"
        gold = "datasets/GISA/answer"

    samples = load_samples(data, gold, limit=args.limit)
    from eval.preprocess import clean_query

    sem = asyncio.Semaphore(args.concurrency)

    async def _one(s):
        q = s.query if hasattr(s, "query") else s.question
        async with sem:
            cq = await clean_query(q)
        return s.id, q, cq

    results = await asyncio.gather(*[_one(s) for s in samples])

    out = []
    for sid, original, cq in results:
        rec = {
            "id": str(sid),
            "original_query": original,
            "cleaned_query": cq.cleaned,
            "extracted_columns": cq.columns,
            "column_formats": cq.column_formats,
            "used_fallback": cq.used_fallback,
            "len_original": len(original),
            "len_cleaned": len(cq.cleaned),
        }
        out.append(rec)
        print("=" * 80)
        print(f"[{sid}] columns={cq.columns} fallback={cq.used_fallback}")
        if cq.column_formats:
            print(f"  formats={json.dumps(cq.column_formats, ensure_ascii=False)}")
        print(f"-- original ({len(original)} chars) --")
        print(original[:600] + ("..." if len(original) > 600 else ""))
        print(f"-- cleaned ({len(cq.cleaned)} chars) --")
        print(cq.cleaned)
        print()

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n[saved] {args.json_out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark", choices=["gisa", "widesearch"], default="widesearch")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--json-out", default=None)
    args = p.parse_args()
    _load_env()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
