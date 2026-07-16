"""Eval CLI entrypoint.

Examples:

    python -m eval.run --benchmark gisa --limit 2 --concurrency 2
    python -m eval.run --benchmark widesearch --ids ws_en_001,ws_en_002
    python -m eval.run --benchmark widesearch --range 5-12   # 1-based, inclusive
    python -m eval.run --benchmark gisa --range 30-          # from #30 to end
    python -m eval.run --benchmark gisa --range 7            # just sample #7
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


def _setup_env() -> None:
    for cand in [Path.cwd() / ".env", Path(__file__).parent.parent / ".env"]:
        if cand.exists():
            load_dotenv(cand)
            break


# Load .env BEFORE any searchos imports — pydantic-settings reads env
# vars at module-import time (settings = Settings()), so they
# must be present before the first `from searchos...` statement.
_setup_env()


def _setup_provider(no_search: bool) -> None:
    if no_search:
        return
    # searchos unifies search + page-fetch onto one provider: set_browser_provider
    # binds the shared _provider that both the search tool (get_provider) and
    # the page fetcher read.
    from searchos.tools.simple_browser.state import set_browser_provider
    from searchos.tools.simple_browser.search import build_search_provider
    # SF_SEARCH_PROVIDER 显式指定后端；无 key 时默认仍是内部 ragflow。
    set_browser_provider(build_search_provider())


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eval.run", description="SearchOS benchmark eval")
    p.add_argument("--benchmark", required=True, choices=["gisa", "widesearch", "xbench"])
    p.add_argument("--data-path", default=None,
                   help="JSONL data path. Default: datasets/<bm>/<bm>_100.jsonl or widesearch.jsonl")
    p.add_argument("--gold-dir", default=None,
                   help="Gold CSV directory. Default: datasets/GISA/answer or datasets/widesearch/widesearch_gold")
    p.add_argument("--output-dir", default=None,
                   help="Where to write per-question results. Default: eval_results/<bm>_<timestamp>")
    p.add_argument("--workspace-root", default=None,
                   help="Override harness workspace root. Default: <output-dir>/sessions/")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--ids", default=None, help="Comma-separated sample ids to include")
    p.add_argument(
        "--range", dest="range_spec", default=None,
        help=(
            "1-based inclusive index range over the (id-filtered) sample "
            "list. Forms: 'N-M' (#N to #M), 'N-' (from #N to end), "
            "'-M' (first M), or 'N' (single sample). Applied after --ids "
            "and before --limit."
        ),
    )
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument(
        "--no-column-hints", dest="column_hints", action="store_false",
        default=True,
        help="Disable golden-derived per-column format hints (schema_hints). "
             "On by default.",
    )
    p.add_argument(
        "--seed-primary-key", dest="seed_primary_key", action="store_true",
        default=False,
        help="Seed the benchmark's unique_columns as a row-identity (primary "
             "key) hint into the query text + schema check. Off by default "
             "(ablation flag; only widesearch samples carry unique_columns).",
    )
    p.add_argument(
        "--no-preprocess-query", dest="preprocess_query", action="store_false",
        default=True,
        help="Use the original benchmark query verbatim. Recommended for fixed-schema "
             "ablations so query-cleaner variance cannot confound the comparison.",
    )
    p.add_argument(
        "--fixed-schema-config", default=None,
        help="JSON file containing per-sample fixed schema variants.",
    )
    p.add_argument(
        "--schema-variant", choices=["single", "multi"], default=None,
        help="Variant selected from --fixed-schema-config.",
    )
    p.add_argument("--no-search", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo = Path(__file__).parent.parent
    if args.benchmark == "gisa":
        data = Path(args.data_path or repo / "datasets/GISA/gisa.jsonl")
        gold = Path(args.gold_dir or repo / "datasets/GISA/answer")
    elif args.benchmark == "xbench":
        # Single CSV holds prompts + gold (inline); no separate gold dir.
        data = Path(args.data_path or repo / "datasets/xbench/DeepSearch-2510.csv")
        gold = Path(args.gold_dir or repo / "datasets/xbench")
    else:
        data = Path(args.data_path or repo / "datasets/widesearch/widesearch.jsonl")
        gold = Path(args.gold_dir or repo / "datasets/widesearch/widesearch_gold")
    if args.output_dir:
        out = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = repo / "eval_results" / f"{args.benchmark}_{ts}"
    return data, gold, out


def _parse_range(spec: str, total: int) -> tuple[int, int]:
    """Parse a 1-based inclusive range spec ('N-M' / 'N-' / '-M' / 'N')
    against a sample count and return Python slice bounds [lo, hi).

    Out-of-range bounds are clamped, not rejected, so 'N-9999' on a
    100-sample run still works.
    """
    raw = (spec or "").strip()
    if not raw:
        return 0, total
    if "-" not in raw:
        n = int(raw)
        if n < 1:
            raise ValueError(f"--range index must be >= 1, got {n}")
        return n - 1, n
    lo_s, hi_s = raw.split("-", 1)
    lo = int(lo_s) if lo_s.strip() else 1
    hi = int(hi_s) if hi_s.strip() else total
    if lo < 1 or hi < lo:
        raise ValueError(f"--range invalid: {spec!r} (need 1<=N<=M)")
    return lo - 1, min(hi, total)


async def _amain(args: argparse.Namespace) -> int:
    _setup_env()
    _setup_provider(args.no_search)
    data_path, gold_dir, output_dir = _resolve_paths(args)
    ids = [s.strip() for s in args.ids.split(",")] if args.ids else None

    if args.benchmark == "gisa":
        from eval.benchmarks.gisa import load_samples, grade
    elif args.benchmark == "xbench":
        from eval.benchmarks.xbench import load_samples, grade
    else:
        from eval.benchmarks.widesearch import load_samples, grade

    # Load full id-filtered set first so --range indexes into the same
    # ordering the user sees. Apply --range, then --limit on top.
    samples = load_samples(data_path, gold_dir, ids=ids)
    if args.range_spec:
        try:
            lo, hi = _parse_range(args.range_spec, len(samples))
        except ValueError as e:
            print(f"[eval] {e}", file=sys.stderr)
            return 2
        samples = samples[lo:hi]
        print(f"[eval] --range {args.range_spec!r} → "
              f"samples #{lo+1}..#{lo+len(samples)} ({len(samples)} kept)")
    if args.limit:
        samples = samples[:args.limit]

    if bool(args.fixed_schema_config) != bool(args.schema_variant):
        print(
            "[eval] --fixed-schema-config and --schema-variant must be used together",
            file=sys.stderr,
        )
        return 2

    fixed_schemas = None
    if args.fixed_schema_config:
        from eval.fixed_schema import (
            load_fixed_schema_variant,
            validate_fixed_schema,
        )

        try:
            fixed_schemas = load_fixed_schema_variant(
                args.fixed_schema_config,
                args.schema_variant,
                sample_ids=[str(sample.id) for sample in samples],
            )
            for sample in samples:
                validate_fixed_schema(
                    fixed_schemas[str(sample.id)],
                    required_columns=sample.required_columns or (),
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[eval] invalid fixed schema config: {exc}", file=sys.stderr)
            return 2

    print(f"[eval] benchmark={args.benchmark} samples={len(samples)} "
          f"concurrency={args.concurrency} output={output_dir}")
    if not samples:
        print("[eval] no samples to run", file=sys.stderr)
        return 1

    from eval.runner import run_benchmark
    summary = await run_benchmark(
        benchmark=args.benchmark,
        samples=samples,
        grade_fn=grade,
        output_dir=output_dir,
        workspace_root=args.workspace_root,
        concurrency=args.concurrency,
        column_hints=args.column_hints,
        seed_primary_key=args.seed_primary_key,
        preprocess_query=args.preprocess_query,
        fixed_schemas=fixed_schemas,
    )
    print("\n[eval] summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[eval] per-question results in {output_dir}")
    return 0


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    rc = asyncio.run(_amain(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
