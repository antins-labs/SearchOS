"""WideSearch benchmark adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from eval.reformat import reformat_for_benchmark, strip_citations
from eval.scorers.widesearch_official.data_loader import (
    WideSearchQuery,
    WideSearchResponse,
    norm_column,
)
from eval.scorers.widesearch_official.evaluation import evaluate_single_query


@dataclass
class WSSample:
    instance_id: str
    query: str
    evaluation: dict
    answer_csv: str
    language: str

    @property
    def benchmark(self) -> str:
        return "widesearch"

    @property
    def id(self) -> str:
        return self.instance_id

    # --- canonical accessors (uniform across benchmarks) ---
    @property
    def answer_type(self) -> str:
        return "table"

    @property
    def gold_csv(self) -> str | None:
        return self.answer_csv

    @property
    def required_columns(self) -> list[str] | None:
        return (self.evaluation or {}).get("required") or None

    @property
    def unique_columns(self) -> list[str] | None:
        """Column set the scorer uses to inner-merge (align) predicted vs gold
        rows — i.e. the row identity / primary key. Only widesearch carries it."""
        return (self.evaluation or {}).get("unique_columns") or None


def load_samples(
    jsonl_path: str | Path,
    gold_dir: str | Path,
    *,
    ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> list[WSSample]:
    jsonl_path = Path(jsonl_path)
    gold_dir = Path(gold_dir)
    keep = set(ids) if ids else None
    out: list[WSSample] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            iid = obj["instance_id"]
            if keep is not None and iid not in keep:
                continue
            ev = obj["evaluation"]
            if isinstance(ev, str):
                ev = json.loads(ev)
            answer_csv = gold_dir / f"{iid}.csv"
            if not answer_csv.exists():
                continue
            out.append(WSSample(
                instance_id=iid,
                query=obj["query"],
                evaluation=ev,
                answer_csv=str(answer_csv),
                language=obj.get("language", "en"),
            ))
            if limit and len(out) >= limit:
                break
    return out


def _build_query(sample: WSSample) -> Optional[WideSearchQuery]:
    answer = pd.read_csv(sample.answer_csv)
    answer.columns = [norm_column(c.strip()) for c in answer.columns]
    required = sample.evaluation["required"]
    for col in required:
        if col not in answer.columns:
            return None
    answer = answer[list(required)]
    return WideSearchQuery(
        instance_id=sample.instance_id,
        query=sample.query,
        evaluation=sample.evaluation,
        answer=answer,
        language=sample.language,
    )


def grade(prediction_text: str, sample: WSSample, *, result_csv_path: Optional[str] = None) -> dict:
    """Score with WideSearch evaluator. ``prediction_text`` may be either:

    * already-reformatted ```markdown ... ``` (when the runner ran the
      LLM join-and-reformat step), or
    * the raw harness output (we'll let ``WideSearchResponse.extract_dataframe``
      handle pipe-table extraction and we strip citations here).
    """
    pred = prediction_text or ""
    if "```markdown" not in pred:
        reformatted, _ = reformat_for_benchmark(pred, target="widesearch")
        pred = reformatted if reformatted is not None else strip_citations(pred)

    query = _build_query(sample)
    if query is None:
        return {
            "instance_id": sample.instance_id,
            "score": 0.0,
            "msg": "answer csv missing required columns",
        }
    response = WideSearchResponse(instance_id=sample.instance_id, response=pred)
    result = evaluate_single_query(query, response, result_save_path=result_csv_path)
    return asdict(result)
