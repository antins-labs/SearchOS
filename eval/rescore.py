"""Re-grade existing eval_result.json directories without re-running harness.

Useful when you change the scorer (e.g. add column-level metrics) and want
to update past runs in place.
"""

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


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _pred_for(qdir: Path, sample) -> str:
    # Item answers are judged from the raw orchestrator output (the lossy
    # reformat-to-cell step can drop the stated fact); other types prefer
    # the LLM-reformatted prediction.
    if (sample.answer_type or "").lower() == "item":
        return _read(qdir / "raw_answer.md") or _read(qdir / "reformatted.md")
    return _read(qdir / "reformatted.md") or _read(qdir / "raw_answer.md")


async def _grade_one(qdir, sample, grade, sem, loop) -> dict | None:
    """Grade a single dir off-thread (judge calls are sync) and persist."""
    sid = qdir.name
    pred = _pred_for(qdir, sample)
    if not pred:
        print(f"  - {sid}: no prediction text on disk", file=sys.stderr)
        return None
    async with sem:
        metrics = await loop.run_in_executor(None, grade, pred, sample)
    rec = json.loads((qdir / "eval_result.json").read_text(encoding="utf-8"))
    rec["metrics"] = metrics
    (qdir / "eval_result.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    score_hint = metrics.get("score") or metrics.get("global_em") or metrics.get("table_row_f1")
    print(f"  ✓ {sid}: rescored ({score_hint=})")
    return rec


async def _amain(args) -> None:
    _load_env()
    repo = Path(__file__).parent.parent
    if args.benchmark == "widesearch":
        from eval.benchmarks.widesearch import load_samples, grade
        data = args.data_path or repo / "datasets/widesearch/widesearch.jsonl"
        gold = args.gold_dir or repo / "datasets/widesearch/widesearch_gold"
    else:
        from eval.benchmarks.gisa import load_samples, grade
        data = args.data_path or repo / "datasets/GISA/gisa.jsonl"
        gold = args.gold_dir or repo / "datasets/GISA/answer"

    run_dir = Path(args.run_dir)
    qdirs = sorted([p for p in run_dir.iterdir() if p.is_dir() and (p / "eval_result.json").exists()])
    ids = [p.name for p in qdirs]
    print(f"[rescore] benchmark={args.benchmark} {len(ids)} samples "
          f"concurrency={args.concurrency}", file=sys.stderr)

    samples = load_samples(data, gold, ids=ids)
    by_id = {str(s.id): s for s in samples}

    sem = asyncio.Semaphore(args.concurrency)
    loop = asyncio.get_running_loop()
    tasks = []
    for qdir in qdirs:
        sample = by_id.get(qdir.name)
        if sample is None:
            print(f"  - {qdir.name}: sample not found in dataset", file=sys.stderr)
            continue
        tasks.append(_grade_one(qdir, sample, grade, sem, loop))
    records = [r for r in await asyncio.gather(*tasks) if r is not None]

    # Aggregate: per-type precision / recall / f1 + overall, written to disk
    # and printed. Uses the same aggregators as a live run.
    if args.benchmark == "gisa":
        from eval.runner import aggregate_gisa
        summary = aggregate_gisa(records)
    else:
        from eval.runner import aggregate_widesearch
        summary = aggregate_widesearch(records)
    summary["n_rescored"] = len(records)
    (run_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[rescore] summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[rescore] wrote {run_dir / '_summary.json'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="e.g. eval_results/widesearch_20260501_142618")
    ap.add_argument("--benchmark", choices=["gisa", "widesearch"], required=True)
    ap.add_argument("--data-path", default=None)
    ap.add_argument("--gold-dir", default=None)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
