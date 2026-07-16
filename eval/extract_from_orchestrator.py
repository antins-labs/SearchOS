"""Re-extract the answer table from each run's orchestrator.json via LLM, then score.

Unlike rescore.py (which re-grades the on-disk reformatted/raw prediction), this
takes the orchestrator's FINAL synthesis turn — the last assistant message that
is not followed by a tool call — and feeds it to the same reformat LLM, then
grades with the same SimpleEvaluator.

Writes results to a separate namespace so the original metrics survive:
  - per case: <qdir>/reformatted_from_orch.md  and  eval_result.json["metrics_from_orch"]
  - run dir:  _summary_from_orch.json
and prints a per-case diff (current metrics vs orchestrator-extracted metrics).
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


def _build_report(orch_path: Path) -> str:
    """Return the orchestrator's final answer turn.

    The last assistant message NOT followed by a tool call is the final
    synthesis (later assistant turns that precede a tool_call are still
    mid-research). We grade exactly that text.
    """
    try:
        data = json.loads(orch_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  - {orch_path.parent.parent.name}: orchestrator.json unreadable ({e})",
              file=sys.stderr)
        return ""
    msgs = data.get("messages", [])
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("role") not in ("assistant", "ai"):
            continue
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        nxt = msgs[i + 1] if i + 1 < len(msgs) else None
        if nxt is not None and nxt.get("role") == "tool_call":
            continue
        return content
    return ""


async def _extract_one(qdir, sample, sem, loop, grade) -> dict | None:
    sid = qdir.name
    orch = qdir / "session" / "conversations" / "orchestrator.json"
    if not orch.exists():
        print(f"  - {sid}: no orchestrator.json", file=sys.stderr)
        return None
    report = _build_report(orch)
    if not report.strip():
        print(f"  - {sid}: empty report", file=sys.stderr)
        return None

    rec = json.loads((qdir / "eval_result.json").read_text(encoding="utf-8"))
    pp = rec.get("preprocess") or {}
    answer_type = (getattr(sample, "answer_type", "table") or "table")

    from eval.reformat import reformat_for_eval
    async with sem:
        pred, _df = await reformat_for_eval(
            report,
            target="gisa",
            answer_type=answer_type,
            original_query=pp.get("cleaned_query") or rec.get("question") or "",
            required_columns=pp.get("columns") or None,
            key_columns=getattr(sample, "unique_columns", None),
            column_formats=pp.get("column_formats") or None,
            sort_hint=pp.get("sort", "") or "",
            filters=pp.get("filters") or None,
        )
    if not pred:
        print(f"  - {sid}: reformat produced nothing", file=sys.stderr)
        return None

    (qdir / "reformatted_from_orch.md").write_text(pred, encoding="utf-8")
    metrics = await loop.run_in_executor(None, grade, pred, sample)
    rec["metrics_from_orch"] = metrics
    (qdir / "eval_result.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    old = rec.get("metrics") or {}
    print(f"  ✓ {sid}: {_key_score(old):.2f} -> {_key_score(metrics):.2f}")
    return rec


def _key_score(m: dict) -> float:
    for k in ("table_row_f1", "list_content_f1", "set_f1", "item_em"):
        if k in m:
            return float(m[k])
    return 0.0


async def _amain(args) -> None:
    _load_env()
    repo = Path(__file__).parent.parent
    from eval.benchmarks.gisa import load_samples, grade
    data = args.data_path or repo / "datasets/GISA/gisa.jsonl"
    gold = args.gold_dir or repo / "datasets/GISA/answer"

    run_dir = Path(args.run_dir)
    qdirs = sorted([p for p in run_dir.iterdir()
                    if p.is_dir() and (p / "eval_result.json").exists()])
    ids = [p.name for p in qdirs]
    print(f"[extract] {len(ids)} samples concurrency={args.concurrency}", file=sys.stderr)

    samples = load_samples(data, gold, ids=ids)
    by_id = {str(s.id): s for s in samples}

    sem = asyncio.Semaphore(args.concurrency)
    loop = asyncio.get_running_loop()
    tasks = []
    for qdir in qdirs:
        sample = by_id.get(qdir.name)
        if sample is None:
            print(f"  - {qdir.name}: sample not in dataset", file=sys.stderr)
            continue
        tasks.append(_extract_one(qdir, sample, sem, loop, grade))
    records = [r for r in await asyncio.gather(*tasks) if r is not None]

    # Aggregate using metrics_from_orch as the live metrics so existing
    # aggregators work unchanged.
    rebound = []
    for r in records:
        r2 = dict(r)
        r2["metrics"] = r.get("metrics_from_orch") or {}
        rebound.append(r2)
    from eval.runner import aggregate_gisa
    summary = aggregate_gisa(rebound)
    summary["n_extracted"] = len(records)
    (run_dir / "_summary_from_orch.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[extract] summary (orchestrator-extracted):")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[extract] wrote {run_dir / '_summary_from_orch.json'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--data-path", default=None)
    ap.add_argument("--gold-dir", default=None)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
