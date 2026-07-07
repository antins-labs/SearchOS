"""GISA benchmark adapter.

Sample loading + per-question grading via vendored ``SimpleEvaluator``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from eval.reformat import reformat_for_benchmark
from eval.scorers.gisa_official import SimpleEvaluator


@dataclass
class GISASample:
    id: str
    question: str
    answer_type: str  # 'table' | 'list' | 'set' | 'item'
    question_type: str
    topic: str
    gt_csv_path: str

    @property
    def benchmark(self) -> str:
        return "gisa"

    # --- canonical accessors (uniform across benchmarks) ---
    @property
    def query(self) -> str:
        return self.question

    @property
    def gold_csv(self) -> str | None:
        return self.gt_csv_path

    @property
    def required_columns(self) -> list[str] | None:
        return None


def load_samples(
    jsonl_path: str | Path,
    gold_dir: str | Path,
    *,
    ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> list[GISASample]:
    jsonl_path = Path(jsonl_path)
    gold_dir = Path(gold_dir)
    keep = set(str(x) for x in ids) if ids else None
    out: list[GISASample] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            qid = str(obj["id"])
            if keep is not None and qid not in keep:
                continue
            csv_path = gold_dir / f"{qid}.csv"
            if not csv_path.exists():
                continue
            out.append(GISASample(
                id=qid,
                question=obj["question"],
                answer_type=obj.get("answer_type", "table"),
                question_type=obj.get("question_type", ""),
                topic=obj.get("topic", ""),
                gt_csv_path=str(csv_path),
            ))
            if limit and len(out) >= limit:
                break
    return out


def grade(prediction_text: str, sample: GISASample) -> dict:
    """Score with SimpleEvaluator. ``prediction_text`` may be either:

    * already-reformatted ```tsv ... ``` (when the runner ran the LLM
      join-and-reformat step), or
    * the raw harness output (in which case we do a rule-only fallback
      extract here).
    """
    evaluator = SimpleEvaluator()
    pred = prediction_text or ""
    # If caller didn't pre-reformat, do rule-only fallback inline.
    if "```tsv" not in pred and "\t" not in pred:
        reformatted, _ = reformat_for_benchmark(pred, target="gisa")
        if reformatted:
            pred = reformatted
    metrics = evaluator.evaluate_one(
        prediction=pred,
        gt_path=sample.gt_csv_path,
        question_type=sample.answer_type,
        qid=sample.id,
    )
    return metrics
