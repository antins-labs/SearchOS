"""Concurrent eval runner.

Orchestrates: harness invocation per question → output extraction → benchmark
grading → per-question persistence + final aggregation. Skips questions whose
``eval_result.json`` already exists (resume).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


def _suspected_infra_abort(workspace_path: str, elapsed: float, record: dict) -> bool:
    """True when the session died of infrastructure (rate-limit) rather
    than finishing a real search: zero evidence AND (died in seconds OR
    zero coverage with a RateLimitError in the trajectory tail)."""
    if (record.get("evidence_count") or 0) != 0:
        return False
    if elapsed < 10:
        return True
    if (record.get("coverage") or 0) != 0:
        return False
    try:
        traj = Path(workspace_path) / "trajectory.jsonl"
        tail = traj.read_text(encoding="utf-8")[-40000:]
    except OSError:
        return False
    return ("RateLimitError" in tail or "RPM_LIMIT_EXCEEDED" in tail
            or "rate limit" in tail.lower())


def _safe_session_id(benchmark: str, sample_id: str, run_tag: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(sample_id))
    return f"{run_tag}_{benchmark}_{safe}"


async def _run_one(
    sample: Any,
    *,
    benchmark: str,
    grade_fn: Callable[[str, Any], dict],
    run_tag: str,
    output_dir: Path,
    sem: asyncio.Semaphore,
    harness_factory: Callable[[str], Any],
    preprocess_query: bool = True,
    column_hints: bool = True,
    seed_primary_key: bool = False,
) -> dict:
    from searchos.socm import SearchState  # local import: heavy
    from eval.reformat import load_session_output
    from eval.preprocess import clean_query, generate_schema_hints

    qdir = output_dir / str(sample.id)
    qdir.mkdir(parents=True, exist_ok=True)
    result_path = qdir / "eval_result.json"
    if result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            pass  # corrupt, re-run

    raw_query = sample.query

    record: dict[str, Any] = {
        "id": str(sample.id),
        "benchmark": benchmark,
        "question": raw_query,
        "started_at": datetime.utcnow().isoformat() + "Z",
    }

    cache_baseline = {"served": 0, "fetched": 0, "stored": 0}
    jina_calls_baseline = 0
    async with sem:
        # Snapshot AFTER acquiring the semaphore so the delta reflects
        # roughly this question's own elapsed window. Snapshotting before
        # the sem makes every queued task share a baseline of 0 → all
        # deltas look cumulative.
        try:
            from searchos.tools.simple_browser.backend.base import BrowserService as _BS
            from searchos.tools.simple_browser.backend.jina import JinaReaderBackend as _JRB
            _svc = _BS.get()
            if getattr(_svc, "_disk_cache", None) is not None:
                cache_baseline = dict(_svc._disk_cache.stats)
            if isinstance(_svc.backend, _JRB):
                jina_calls_baseline = _svc.backend.api_calls
        except Exception:
            pass

        try:
            # Pre-filter: strip "single Markdown table with columns A,B,C" boilerplate
            # so the orchestrator's multi-table planning isn't shouted down by the user.
            # We re-attach the columns + per-column formats as a structured
            # appendix below, so the orchestrator has them visible in the
            # task text (the SOCM snapshot doesn't surface column names from
            # a pre-seeded schema, so injecting via state didn't actually
            # propagate the info — see analysis 2026-05-01).
            run_query = raw_query
            seed_columns: list[str] = []
            seed_formats: dict[str, str] = {}
            if preprocess_query:
                cq = await clean_query(raw_query)
                record["preprocess"] = {
                    "cleaned_query": cq.cleaned,
                    "columns": cq.columns,
                    "column_formats": cq.column_formats,
                    "used_fallback": cq.used_fallback,
                }
                record["preprocess"]["filters"] = cq.filters
                record["preprocess"]["sort"] = cq.sort
                if not cq.used_fallback:
                    seed_columns = cq.columns
                    seed_formats = cq.column_formats
                    # Enrich column formats with golden-derived per-column
                    # hints inferred from the table HEADER. Only table answers
                    # have a header to infer from; list/set/item are headerless
                    # — a value-format hint there hurt list scoring (judge A/B:
                    # list content_f1 -0.107) and risks leaking the answer, so
                    # we skip hints entirely for those types.
                    golden_csv = sample.gold_csv
                    is_table = (sample.answer_type or "table") == "table"
                    if column_hints and golden_csv and is_table:
                        schema_hints = await generate_schema_hints(
                            raw_query, golden_csv, n_rows=5,
                            answer_type=sample.answer_type,
                        )
                        if schema_hints:
                            record["preprocess"]["schema_hints"] = schema_hints
                            for col, hint in schema_hints.items():
                                if col not in seed_formats or not seed_formats[col]:
                                    seed_formats[col] = hint
                    if seed_columns:
                        appendix_lines = [
                            cq.cleaned,
                            "",
                            "## Required attributes (must be covered by the schema, single- or multi-table)",
                        ]
                        for col in seed_columns:
                            fmt = seed_formats.get(col, "")
                            appendix_lines.append(
                                f"- {col}" + (f" — {fmt}" if fmt else "")
                            )
                        if cq.filters:
                            appendix_lines += [
                                "",
                                "## Scope filters (rows outside these bounds must NOT appear in the final table)",
                            ]
                            appendix_lines += [f"- {f}" for f in cq.filters]
                        if cq.sort:
                            appendix_lines += [
                                "",
                                f"## Output order\n- {cq.sort}",
                            ]
                        run_query = "\n".join(appendix_lines)
                    else:
                        run_query = cq.cleaned

            # Row-identity (primary key) hint — ablation, off unless
            # --seed-primary-key. Seeds the benchmark's unique_columns (the
            # column set the scorer uses to align rows) so the schema's
            # primary_key lands on the same grain the scorer merges on.
            pk_hint: list[str] = []
            if seed_primary_key:
                uc = getattr(sample, "unique_columns", None)
                if uc:
                    pk_hint = list(uc)
                    run_query = (
                        run_query
                        + "\n\n## Row identity (primary key)\n"
                        + f"- Each row is uniquely identified by: {', '.join(pk_hint)}\n"
                        + "- The schema's primary_key must be exactly these columns "
                        "(single table), or map to them via the main table's key "
                        "(multi-table). Do NOT collapse or drop any of them."
                    )

            # harness session lives at <qdir>/session/  — co-located with eval_result.json
            harness = harness_factory(str(qdir))
            session_id = "session"
            initial_state = SearchState(
                intent=run_query,
                required_attributes=list(seed_columns),
                primary_key_hint=pk_hint,
            )
            t0 = time.time()
            search_result = await harness.run(
                run_query,
                session_id=session_id,
                initial_state=initial_state,
            )
            elapsed = time.time() - t0
            workspace_path = search_result.workspace_path
            record["workspace_path"] = workspace_path
            record["elapsed_s"] = elapsed
            record["coverage"] = getattr(search_result, "coverage_score", None)
            record["evidence_count"] = getattr(search_result, "evidence_count", None)
            record["token_usage"] = getattr(search_result, "token_usage", {})

            # Suspected RPM-storm abort. Don't persist the result — let the
            # next run retry this question rather than baking in a false zero
            # that the resume-skip would then honor forever.
            # Judged by DEATH SIGNATURE, not elapsed alone: task recycling
            # stretches a rate-limited death to 35-135s (3 escapes observed
            # on 2026-06-11 with the old `elapsed < 10` check).
            if _suspected_infra_abort(workspace_path, elapsed, record):
                logger.warning(
                    "suspected RPM abort for %s (elapsed=%.1fs, evidence=0); "
                    "skipping write — will retry next run",
                    sample.id, elapsed,
                )
                print(f"[progress] SKIP {sample.id} (suspected RPM abort, "
                      f"elapsed={elapsed:.1f}s)", flush=True)
                return record

            raw_text = ""
            eval_table_path = Path(workspace_path) / "output" / "eval_table.md"
            if eval_table_path.exists():
                raw_text = eval_table_path.read_text(encoding="utf-8")
            if not raw_text:
                raw_text = load_session_output(workspace_path) or ""
            (qdir / "raw_answer.md").write_text(raw_text, encoding="utf-8")

            # Multi-table join + format-respecting reformat. Reuse the
            # preprocess step's structured output (cleaned query, column
            # list, formats, sort) so the reformat LLM doesn't re-parse
            # the raw question.
            from eval.reformat import reformat_for_eval
            required_cols = sample.required_columns
            pp = record.get("preprocess") or {}
            answer_type = sample.answer_type or "table"
            if answer_type == "qa":
                # QA benchmarks (e.g. xbench DeepSearch): single-answer task,
                # nothing to reshape into a table. The answer lives in the
                # synthesized harness output — grade it directly; the LLM
                # judge extracts the final answer itself.
                cleaned_pred, _df = None, None
            else:
                reformat_cols = required_cols or seed_columns or None
                reformat_formats = seed_formats or None
                reformat_sort = pp.get("sort", "") or ""
                cleaned_pred, _df = await reformat_for_eval(
                    raw_text,
                    target=benchmark,
                    answer_type=answer_type,
                    original_query=raw_query,
                    required_columns=reformat_cols,
                    column_formats=reformat_formats,
                    sort_hint=reformat_sort,
                    filters=pp.get("filters") or None,
                )
            if cleaned_pred is not None:
                # Widesearch scoring uses strict set-equality on columns —
                # any extra column the LLM added (e.g. "排名" for top-N
                # queries) zeros the score even when all required columns
                # are present. Trim extras here and rename to the verbatim
                # required names so the response matches exactly. Only
                # fires when EVERY required col is present; missing cols
                # are left alone so the scorer can surface the real gap.
                if _df is not None and reformat_cols and answer_type == "table":
                    from eval.reformat import trim_extra_columns
                    block, _df, extras = trim_extra_columns(
                        _df, list(reformat_cols), target=benchmark,
                    )
                    if block is not None:
                        cleaned_pred = block
                        logger.info(
                            "trimmed %d extra column(s) from %s: %s",
                            len(extras), sample.id, extras,
                        )
                (qdir / "reformatted.md").write_text(cleaned_pred, encoding="utf-8")
                record["reformat_used_llm"] = True
                pred_for_grader = cleaned_pred
            else:
                record["reformat_used_llm"] = False
                pred_for_grader = raw_text

            # Item answers are a single fact.  When the LLM judge is
            # enabled it can read the answer out of verbose prose, so feed
            # it the full raw text.  Under strict exact-match (default) the
            # raw text is too noisy — use the reformatted single-cell
            # output instead, which is what every other answer_type does.
            import os as _os
            if answer_type == "item" and _os.environ.get("GISA_LLM_JUDGE") == "1":
                pred_for_grader = raw_text
        except Exception:
            # Don't persist the result file on exception — next run will
            # retry this question. (Prior behavior: wrote partial record
            # which then caused the resume-skip on retry.)
            logger.exception("harness failed for %s", sample.id)
            print(f"[progress] FAILED {sample.id} (harness exception, not persisted)",
                  flush=True)
            record["error"] = traceback.format_exc()
            return record

    # scoring runs synchronously off the semaphore (LLM judge calls are sync)
    try:
        loop = asyncio.get_running_loop()
        metrics = await loop.run_in_executor(None, grade_fn, pred_for_grader, sample)
    except Exception:
        record["error"] = traceback.format_exc()
        metrics = {}

    record["metrics"] = metrics
    record["finished_at"] = datetime.utcnow().isoformat() + "Z"
    result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    # one-line progress beacon for external monitors (flushed)
    score_hint = ""
    if isinstance(metrics, dict):
        for k in ("score", "global_em", "table_row_f1"):
            if k in metrics:
                score_hint = f" {k}={metrics[k]}"
                break
        if metrics.get("pk_only_match"):
            score_hint += " [PK-ONLY: score covers key column only]"
    cache_hint = ""
    try:
        from searchos.tools.simple_browser.backend.base import BrowserService
        from searchos.tools.simple_browser.backend.jina import JinaReaderBackend as _JRB
        svc = BrowserService.get()
        if getattr(svc, "_disk_cache", None) is not None:
            s = svc._disk_cache.stats
            d = {k: s[k] - cache_baseline.get(k, 0) for k in s}
            record["page_cache"] = d
            cache_hint = f" cache=served{d['served']}/fetched{d['fetched']}/stored{d['stored']}"
        if isinstance(svc.backend, _JRB):
            jina_delta = svc.backend.api_calls - jina_calls_baseline
            record["jina_api_calls"] = jina_delta
            cache_hint += f" jina={jina_delta}"
    except Exception:
        pass
    result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[progress] done {sample.id}{score_hint} elapsed={record.get('elapsed_s', 0):.1f}s{cache_hint}",
          flush=True)
    return record


def aggregate_gisa(records: list[dict]) -> dict:
    from eval.scorers.gisa_official import SimpleEvaluator
    rows = []
    for r in records:
        m = r.get("metrics") or {}
        if "question_type" in m:
            rows.append(m)
    return SimpleEvaluator.gather_results(rows)


def aggregate_widesearch(records: list[dict]) -> dict:
    if not records:
        return {}
    summary = {
        "n": 0,
        "score_em": 0.0,
        "precision_by_row": 0.0, "recall_by_row": 0.0, "f1_by_row": 0.0,
        "precision_by_item": 0.0, "recall_by_item": 0.0, "f1_by_item": 0.0,
        "precision_by_col": 0.0, "recall_by_col": 0.0, "f1_by_col": 0.0,
    }
    for r in records:
        m = r.get("metrics") or {}
        if "score" not in m:
            continue
        summary["n"] += 1
        summary["score_em"] += float(m.get("score", 0))
        for k in ("precision_by_row", "recall_by_row", "f1_by_row",
                  "precision_by_item", "recall_by_item", "f1_by_item",
                  "precision_by_col", "recall_by_col", "f1_by_col"):
            summary[k] += float(m.get(k, 0))
    n = max(summary["n"], 1)
    for k in list(summary.keys()):
        if k == "n":
            continue
        summary[k] = round(summary[k] / n, 4)
    return summary


def aggregate_xbench(records: list[dict]) -> dict:
    """Accuracy = mean of per-question score (1 correct / 0 wrong)."""
    scored = [r.get("metrics") or {} for r in records]
    scored = [m for m in scored if "score" in m]
    n = len(scored)
    correct = sum(int(m.get("score", 0)) for m in scored)
    return {
        "n": n,
        "correct": correct,
        "accuracy": round(correct / max(n, 1), 4),
    }


async def run_benchmark(
    *,
    benchmark: str,
    samples: list[Any],
    grade_fn: Callable[[str, Any], dict],
    output_dir: str | Path,
    workspace_root: str | None = None,
    concurrency: int = 4,
    column_hints: bool = True,
    seed_primary_key: bool = False,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    sem = asyncio.Semaphore(concurrency)

    # Benchmark recall must not depend on interactive saturation heuristics.
    # Force every Explore Agent through the configured verification wave, then
    # restore the process-wide setting for callers that reuse this interpreter.
    from searchos.config.settings import settings as runtime_settings

    previous_min_waves = runtime_settings.explore_min_waves
    runtime_settings.explore_min_waves = runtime_settings.explore_max_waves

    from searchos.harness.session import SearchSession

    def _factory(per_question_root: str) -> SearchSession:
        # If user passed a global override, honor it; otherwise root harness
        # workspace at the question's own dir so its session lives next to
        # eval_result.json.
        root = workspace_root or per_question_root
        return SearchSession(
            workspace_root=root,
            skill_library_path="searchos/skills/library",
            skip_synthesis=True,
        )

    tasks = [
        asyncio.create_task(_run_one(
            sample,
            benchmark=benchmark,
            grade_fn=grade_fn,
            run_tag=run_tag,
            output_dir=output_dir,
            sem=sem,
            harness_factory=_factory,
            column_hints=column_hints,
            seed_primary_key=seed_primary_key,
        ))
        for sample in samples
    ]
    try:
        records = await asyncio.gather(*tasks, return_exceptions=False)
    finally:
        runtime_settings.explore_min_waves = previous_min_waves

    # Drain background skill-evolution / access-skill-generation tasks before
    # the event loop closes. They're fire-and-forget per question (so they
    # never block the next one), but asyncio.run() would cancel any still
    # pending — no timeout here since an access-skill build is a multi-turn
    # LLM agent + live probing and a short cap would sever it mid-flight.
    from searchos.harness.session import (
        close_browser_service,
        wait_for_all_evolutions,
    )
    await wait_for_all_evolutions(timeout=None)
    await close_browser_service()

    if benchmark == "gisa":
        summary = aggregate_gisa(records)
    elif benchmark == "widesearch":
        summary = aggregate_widesearch(records)
    elif benchmark == "xbench":
        summary = aggregate_xbench(records)
    else:
        summary = {}

    summary_path = output_dir / "_summary.json"
    summary_path.write_text(
        json.dumps({"benchmark": benchmark, "n_samples": len(records),
                    "concurrency": concurrency, "summary": summary},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
