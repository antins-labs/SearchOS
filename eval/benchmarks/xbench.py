"""xbench-DeepSearch benchmark adapter.

Single-answer QA (not a table benchmark). Source data
(``datasets/xbench/DeepSearch-2510.csv``) is base64 + XOR(canary)
obfuscated at rest — an anti-contamination canary asks that it never
appear as plaintext online — so we decode in-memory at load time and
do not modify or publish the source dataset. Local eval artifacts contain
question, prediction and gold for reproducibility; do not publish them.

Predictions are the orchestrator's last answer, without table reformatting.
Uses the shared custom QA judge, not the official xbench grading protocol.
"""

from __future__ import annotations

import base64
import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class XBenchSample:
    id: str
    question: str          # decoded prompt (runner reads .question, see runner:71)
    answer: str            # decoded gold answer
    answer_type: str = "qa"  # signals the runner to SKIP table reformat
    reference_steps: str = ""

    # --- canonical accessors (uniform across benchmarks) ---
    @property
    def query(self) -> str:
        return self.question

    @property
    def gold_csv(self) -> str | None:
        return None

    @property
    def required_columns(self) -> list[str] | None:
        return None

    @property
    def benchmark(self) -> str:
        return "xbench"


# --- decode (base64 then XOR with the row's canary) ---------------------
def _xor(data: bytes, key: str) -> bytes:
    kb = key.encode("utf-8")
    return bytes(data[i] ^ kb[i % len(kb)] for i in range(len(data)))


def _decode(field: str, canary: str) -> str:
    return _xor(base64.b64decode(field), canary).decode("utf-8")


def load_samples(
    data_path: str | Path,
    gold_dir: str | Path | None = None,  # unused — gold is inline; kept for parity
    *,
    ids: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> list[XBenchSample]:
    data_path = Path(data_path)
    keep = set(str(x) for x in ids) if ids else None
    out: list[XBenchSample] = []
    with data_path.open(encoding="utf-8") as f:
        rows = (json.loads(line) for line in f if line.strip()) if data_path.suffix == ".jsonl" else csv.DictReader(f)
        seen = set()
        for row in rows:
            qid = str(row["id"])
            if not qid or qid in (".", "..") or Path(qid).name != qid or qid in seen:
                raise ValueError(f"xbench: duplicate or unsafe id={qid}")
            seen.add(qid)
            if keep is not None and qid not in keep:
                continue
            try:
                canary = row.get("canary")
                if canary:
                    question = _decode(row["prompt"], canary)
                    answer = _decode(row["answer"], canary)
                else:
                    question = row.get("question", row.get("prompt"))
                    answer = row["answer"]
                if not isinstance(question, str) or not question.strip() or answer is None:
                    raise ValueError("missing question/answer")
                answer = str(answer)
            except Exception:
                raise ValueError(f"xbench: failed to decode row id={qid}")
            out.append(XBenchSample(
                id=qid,
                question=question,
                answer=answer,
                reference_steps=row.get("reference_steps", ""),
            ))
    if keep is not None and keep - seen:
        raise ValueError(f"xbench: unknown IDs {sorted(keep - seen)}")
    return out[:limit] if limit is not None else out


async def grade(prediction_text: str, sample: XBenchSample) -> dict:
    from eval.qa import judge_answer
    return await judge_answer(prediction_text, sample)
