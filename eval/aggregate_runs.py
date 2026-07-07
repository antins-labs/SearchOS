"""Aggregate multiple widesearch eval runs into summary.json + detailed.csv.

Each "run" is one logical pass over the benchmark, made of one or more
output dirs (e.g. an en dir + a zh dir). Produces, per language bucket
(en / zh / all) and per metric:

    run1, run2, ...        — macro-mean over that run's completed questions
    avg@N                  — mean of the per-run values
    max@N                  — best-of-N: per question take the max across
                             runs (union of question ids), then mean

Question id prefix decides the language bucket: ws_en_* / ws_zh_*.

Usage
-----
    # positional: each run is a '+'-joined list of dirs
    python -m eval.aggregate_runs \
        --run eval_results/widesearch_1-50_keyMAIN_A+eval_results/widesearch_101-150_keyD_A \
        --run eval_results/widesearch_1-50_keyMAIN_B+eval_results/widesearch_101-150_keyD_B \
        --out-dir eval_results/exports

Writes <out-dir>/widesearch_summary.json and widesearch_summary_detailed.csv.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os

# (csv metric name, eval_result.metrics field)
METRICS = [
    ("em", "score"),
    ("row_f1", "f1_by_row"),
    ("row_precision", "precision_by_row"),
    ("row_recall", "recall_by_row"),
    ("item_f1", "f1_by_item"),
    ("item_precision", "precision_by_item"),
    ("item_recall", "recall_by_item"),
    ("col_f1", "f1_by_col"),
    ("col_precision", "precision_by_col"),
    ("col_recall", "recall_by_col"),
]
LANGS = ["en", "zh", "all"]


def _load_run(dirs: list[str]) -> dict[str, dict]:
    """{question_id: metrics} for one run (union of its dirs)."""
    out: dict[str, dict] = {}
    for d in dirs:
        for f in glob.glob(f"{d}/*/eval_result.json"):
            qid = os.path.basename(os.path.dirname(f))
            try:
                out[qid] = json.load(open(f, encoding="utf-8")).get("metrics", {})
            except Exception:
                pass
    return out


def _g(m: dict, k: str) -> float:
    return float(m.get(k, 0) or 0)


def _lang_ids(all_ids: set[str], lang: str) -> list[str]:
    if lang == "en":
        return sorted(q for q in all_ids if q.startswith("ws_en"))
    if lang == "zh":
        return sorted(q for q in all_ids if q.startswith("ws_zh"))
    return sorted(all_ids)


def aggregate(runs: dict[str, list[str]]) -> dict:
    """runs = {run_label: [dir, ...]}. Returns nested summary dict."""
    qs = {label: _load_run(dirs) for label, dirs in runs.items()}
    labels = list(runs)
    all_ids = set().union(*[set(v) for v in qs.values()]) if qs else set()

    summary: dict = {}
    for lang in LANGS:
        ids = _lang_ids(all_ids, lang)
        summary[lang] = {"n_questions": len(ids), "metrics": {}}
        for mname, key in METRICS:
            vals = {}
            for lab in labels:
                present = [qs[lab][q] for q in ids if q in qs[lab]]
                vals[lab] = round(sum(_g(m, key) for m in present) / len(present), 4) if present else None
            run_vals = [vals[lab] for lab in labels if vals[lab] is not None]
            avg_n = round(sum(run_vals) / len(run_vals), 4) if run_vals else None
            per = [
                max(_g(qs[lab][q], key) for lab in labels if q in qs[lab])
                for q in ids
                if any(q in qs[lab] for lab in labels)
            ]
            max_n = round(sum(per) / len(per), 4) if per else None
            summary[lang]["metrics"][mname] = {**vals, "avg@N": avg_n, "max@N": max_n}

    coverage = {
        lab: {
            "en": sum(1 for q in qs[lab] if q.startswith("ws_en")),
            "zh": sum(1 for q in qs[lab] if q.startswith("ws_zh")),
            "total": len(qs[lab]),
        }
        for lab in labels
    }
    return {"runs": runs, "coverage": coverage, "summary": summary}


def write_outputs(result: dict, out_dir: str) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    labels = list(result["runs"])
    json_path = os.path.join(out_dir, "widesearch_summary.json")
    json.dump(result, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    csv_path = os.path.join(out_dir, "widesearch_summary_detailed.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lang", "metric"] + labels + ["avg@N", "max@N"])
        for lang in LANGS:
            for mname, _ in METRICS:
                cell = result["summary"][lang]["metrics"][mname]
                w.writerow([lang, mname] + [cell[lab] for lab in labels] + [cell["avg@N"], cell["max@N"]])
    return json_path, csv_path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eval.aggregate_runs", description=__doc__)
    p.add_argument(
        "--run", action="append", required=True, dest="runs",
        help="One run = '+'-joined output dirs (repeat --run per run).",
    )
    p.add_argument("--out-dir", default="eval_results/exports")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    runs = {f"run{i+1}": spec.split("+") for i, spec in enumerate(args.runs)}
    result = aggregate(runs)
    jp, cp = write_outputs(result, args.out_dir)

    for lang in LANGS:
        s = result["summary"][lang]
        m = s["metrics"]
        print(f"[{lang}] n={s['n_questions']}")
        for k in ("em", "row_f1", "item_f1", "col_f1"):
            v = m[k]
            runs_str = " ".join(f"{lab}={v[lab]}" for lab in runs)
            print(f"   {k:9s} {runs_str} avg@N={v['avg@N']} max@N={v['max@N']}")
    print(f"\nwrote {jp}\nwrote {cp}")


if __name__ == "__main__":
    main()
