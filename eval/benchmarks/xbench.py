"""xbench-DeepSearch benchmark adapter.

Single-answer QA (not a table benchmark). Source data
(``datasets/xbench/DeepSearch-2510.csv``) is base64 + XOR(canary)
obfuscated at rest — an anti-contamination canary asks that it never
appear as plaintext online — so we decode in-memory at load time and
never write the decoded prompt/answer to disk.

Our harness still does what it always does (build a table / synthesize
a report); for grading we DON'T reshape that into a table. We take the
synthesized output as-is and let an LLM judge extract the final answer
from it and compare to gold (正确/错误 → 1/0). Judge prompt + parsing
are ported from the official ``datasets/xbench/reference/eval_grader.py``.
"""

from __future__ import annotations

import base64
import csv
import logging
import re
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
        for row in csv.DictReader(f):
            qid = str(row["id"])
            if keep is not None and qid not in keep:
                continue
            canary = row["canary"]
            try:
                question = _decode(row["prompt"], canary)
                answer = _decode(row["answer"], canary)
            except Exception:
                logger.warning("xbench: failed to decode row id=%s; skipping", qid)
                continue
            out.append(XBenchSample(
                id=qid,
                question=question,
                answer=answer,
                reference_steps=row.get("reference_steps", ""),
            ))
            if limit and len(out) >= limit:
                break
    return out


# --- grading (LLM judge, ported from reference/eval_grader.py) ----------
LLM_JUDGE_PROMPT = """
你是一个通用人工智能助手。根据下面给出的[正确答案], 判断以下对[原问题]的[回答]的回答是否正确。

[原问题]: {question}

[正确答案]: {correct_answer}

[回答]:{response}

你的判断必须按照以下格式和标准进行:

最终答案: 从[回答]中提取出的最终准确答案。如果[回答]中没有明确的最终答案, 则填写'无'。

解释: 根据[正确]解释为什么[最终答案]是正确的或错误的。只关注[最终答案]与[正确答案]之间是否存在实质性差异, 不要评论题目的背景, 不要尝试重新解题, 不要为任何不同于[正确答案]的答案辩护, 只专注于判断答案是否一致。

结论: 如果[最终答案]与上方给出的[正确答案]一致, 或者在数值题目中处于可接受的微小误差范围内, 则填写'正确'; 否则（即存在任何不一致、歧义、不等价或提取出的答案错误的情况）填写'错误'。
""".strip()

_FINAL_RE = re.compile(r"最终答案[:：]\s*(.+)")
_CONCL_RE = re.compile(r"结论[:：]\s*.*?(正确|错误)")

# Cap the prediction fed to the judge — the synthesized answer is short,
# but a stray full report shouldn't blow the judge's context window.
_PRED_CHAR_CAP = 12000


def _first(pattern: re.Pattern, text: str) -> str:
    m = pattern.search(text or "")
    return m.group(1).strip() if m else ""


def grade(prediction_text: str, sample: XBenchSample) -> dict:
    """LLM-judge grade for a single QA prediction.

    1. Cheap path: if the output already ends with ``最终答案: X`` and X
       string-equals gold, score 1 without an LLM call.
    2. Otherwise hand (question, gold, our output) to the judge model
       (role ``judge`` → glm5-judge) and parse its 结论.

    Returns ``{score: 0|1, ...}`` so the runner's score-aggregation works.
    Called synchronously from a thread (runner uses run_in_executor), so a
    blocking ``judge.invoke`` is fine.
    """
    pred = (prediction_text or "").strip()
    gold = (sample.answer or "").strip()
    if not pred:
        return {"score": 0, "extracted": "", "method": "empty_prediction", "gold": gold}

    direct = _first(_FINAL_RE, pred)
    if direct and direct == gold:
        return {"score": 1, "extracted": direct, "method": "direct_match", "gold": gold}

    from searchos.config.models import get_model_for
    judge = get_model_for("judge")
    prompt = LLM_JUDGE_PROMPT.format(
        question=sample.question,
        correct_answer=gold,
        response=pred[:_PRED_CHAR_CAP],
    )
    try:
        resp = judge.invoke(prompt)
        out = resp.content if hasattr(resp, "content") else str(resp)
        if isinstance(out, list):
            out = "".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in out
            )
    except Exception as e:  # noqa: BLE001 — a judge failure must not crash the run
        logger.warning("xbench judge failed for %s: %s", sample.id, e)
        return {"score": 0, "extracted": "", "method": "judge_error",
                "error": str(e)[:200], "gold": gold}

    conclusion = _first(_CONCL_RE, out)
    extracted = _first(_FINAL_RE, out)
    return {
        "score": 1 if conclusion == "正确" else 0,
        "extracted": extracted,
        "conclusion": conclusion,
        "method": "llm_judge",
        "gold": gold,
    }
