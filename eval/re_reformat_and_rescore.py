"""Re-export, re-reformat, and re-grade an existing run directory.

For every question dir under <run_dir>:
  1. Read raw_answer.md, or rebuild it from session/search_state.json
  2. Re-run join_and_reformat_with_llm with the question text
     (from eval_result.json["question"], else dataset lookup)
  3. Write raw_answer.md, reformatted.md, and eval_result.json to either
     the source directory or a separate --output-dir
  4. Re-grade and replace eval_result.json["metrics"] in the destination

Concurrency is at the per-question level (LLM calls are async). Harness
is NOT re-run — purely a post-processing rescore.
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


def _load_raw_answer(qdir: Path, *, reexport_search_state: bool) -> str:
    if not reexport_search_state:
        raw_path = qdir / "raw_answer.md"
        return raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""

    state_path = qdir / "session" / "search_state.json"
    if not state_path.exists():
        return ""
    from searchos.harness.report.eval_table_export import build_eval_table
    from searchos.socm import SearchState

    state = SearchState.model_validate_json(state_path.read_text(encoding="utf-8"))
    return build_eval_table(state)


async def _process_one(
    source_qdir: Path,
    target_qdir: Path,
    sample,
    benchmark: str,
    grade_fn,
    sem: asyncio.Semaphore,
    *,
    reexport_search_state: bool,
) -> tuple[str, dict]:
    from eval.reformat import reformat_for_eval

    sid = source_qdir.name
    raw = _load_raw_answer(
        source_qdir, reexport_search_state=reexport_search_state
    )

    source_rec_path = source_qdir / "eval_result.json"
    rec = json.loads(source_rec_path.read_text(encoding="utf-8"))
    question = rec.get("question") or getattr(sample, "query", None) or getattr(sample, "question", None) or ""

    required_cols = None
    if hasattr(sample, "evaluation"):
        ev = sample.evaluation or {}
        required_cols = ev.get("required") or None
    answer_type = getattr(sample, "answer_type", "table") or "table"
    pp = rec.get("preprocess") or {}

    target_qdir.mkdir(parents=True, exist_ok=True)
    (target_qdir / "raw_answer.md").write_text(raw, encoding="utf-8")
    source_session = source_qdir / "session"
    target_session = target_qdir / "session"
    if source_session.is_dir() and not target_session.exists():
        target_session.symlink_to(source_session.resolve(), target_is_directory=True)

    async with sem:
        cleaned_pred, _df = await reformat_for_eval(
            raw, target=benchmark, answer_type=answer_type,
            original_query=question,
            required_columns=required_cols or pp.get("columns") or None,
            key_columns=getattr(sample, "unique_columns", None),
            column_formats=pp.get("column_formats") or None,
            sort_hint=pp.get("sort", "") or "",
            filters=pp.get("filters") or None,
        )

    if cleaned_pred is not None and _df is not None and required_cols and answer_type == "table":
        from eval.reformat import trim_extra_columns
        block, _df, extras = trim_extra_columns(
            _df, list(required_cols), target=benchmark,
        )
        if block is not None:
            cleaned_pred = block
            print(f"  - {sid}: trimmed extras {extras}", file=sys.stderr)

    if cleaned_pred is not None:
        (target_qdir / "reformatted.md").write_text(cleaned_pred, encoding="utf-8")
        rec["reformat_used_llm"] = True
        pred_for_grader = cleaned_pred
    else:
        rec["reformat_used_llm"] = False
        pred_for_grader = raw

    loop = asyncio.get_running_loop()
    metrics = await loop.run_in_executor(None, grade_fn, pred_for_grader, sample)
    original_metrics = rec.get("metrics")
    rec["metrics"] = metrics
    rec["postprocess"] = {
        "source_result": str(source_rec_path),
        "reexport_search_state": reexport_search_state,
        "original_metrics": original_metrics,
    }
    target_rec_path = target_qdir / "eval_result.json"
    target_rec_path.write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    score = (
        metrics.get("f1_by_item")
        or metrics.get("table_row_f1")
        or metrics.get("score")
        or metrics.get("global_em")
        or 0
    )
    return sid, {"score_hint": score}


async def _main_async(args):
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
    output_dir = Path(args.output_dir) if args.output_dir else run_dir
    if args.reexport_search_state and output_dir.resolve() == run_dir.resolve():
        raise ValueError(
            "--reexport-search-state requires a separate --output-dir "
            "so original results are preserved"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    qdirs = sorted([p for p in run_dir.iterdir() if p.is_dir() and (p / "eval_result.json").exists()])
    ids = [p.name for p in qdirs]
    print(
        f"[re-reformat] benchmark={args.benchmark} run_dir={run_dir} "
        f"output_dir={output_dir} n={len(ids)} "
        f"reexport={args.reexport_search_state}",
        file=sys.stderr,
    )

    samples = load_samples(data, gold, ids=ids)
    by_id = {str(s.id) if hasattr(s, "id") else s.instance_id: s for s in samples}

    sem = asyncio.Semaphore(args.concurrency)
    tasks = []
    for qdir in qdirs:
        target_qdir = output_dir / qdir.name
        if args.resume and (target_qdir / "eval_result.json").exists():
            print(f"  - {qdir.name}: already complete", file=sys.stderr)
            continue
        sample = by_id.get(qdir.name)
        if sample is None:
            print(f"  - {qdir.name}: sample not found in dataset", file=sys.stderr)
            continue
        tasks.append(_process_one(
            qdir,
            target_qdir,
            sample,
            args.benchmark,
            grade,
            sem,
            reexport_search_state=args.reexport_search_state,
        ))

    done = 0
    for coro in asyncio.as_completed(tasks):
        sid, info = await coro
        done += 1
        print(f"  [{done}/{len(tasks)}] {sid}: {info}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="dir containing per-question eval_result.json subdirs")
    ap.add_argument("--benchmark", choices=["gisa", "widesearch"], required=True)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--data-path", default=None)
    ap.add_argument("--gold-dir", default=None)
    ap.add_argument(
        "--output-dir",
        default=None,
        help="Write post-processed results here instead of overwriting run_dir.",
    )
    ap.add_argument(
        "--reexport-search-state",
        action="store_true",
        help="Rebuild raw_answer.md from session/search_state.json using the current exporter.",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Skip destination questions that already contain eval_result.json.",
    )
    args = ap.parse_args()
    _load_env()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
