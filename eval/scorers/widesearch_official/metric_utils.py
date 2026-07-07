"""Vendored WideSearch metric utilities (LLM swapped to local shim, no Volcano)."""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional
from urllib.parse import urlparse

import dateparser

from .llm_shim import llm_completion

logger = logging.getLogger(__name__)

preprocess_function_registry = {}
metric_function_registry = {}


def register_preprocess_function(func: Callable):
    preprocess_function_registry[func.__name__] = func
    return func


def register_metric_function(func: Callable):
    metric_function_registry[func.__name__] = func
    return func


# ---------- preprocess ----------

@register_preprocess_function
def extract_number(content: str):
    nums = re.findall(r"[-+]?\d*\.\d+%?|[-+]?\d+\.?\d*%?", str(content).replace(",", ""))
    return nums[0] if nums else "NULL"


# Representational variants that carry no semantic difference. Folded
# symmetrically on both prediction and reference, so this only collapses
# surface forms (it cannot inflate a genuine value mismatch).
_UNICODE_FOLD = {
    "×": "x",   # × multiplication sign → ascii x
    "✕": "x", "✖": "x", "✗": "x",
    "–": "-", "—": "-", "−": "-",  # en/em dash, minus → hyphen
    " ": " ", "　": " ",                 # nbsp, ideographic space
    "％": "%",                                # full-width percent
    "‘": "'", "’": "'",                 # curly single quotes
    "“": '"', "”": '"',                 # curly double quotes
}


def _fold_unicode(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(_UNICODE_FOLD.get(c, c) for c in s)


@register_preprocess_function
def norm_str(content):
    return _fold_unicode(str(content)).lower().strip().replace(" ", "").replace("*", "")


@register_preprocess_function
def norm_date(content):
    d = dateparser.parse(str(content), settings={"PREFER_DAY_OF_MONTH": "first"})
    return d.strftime("%Y-%m-%d") if d else content


# ---------- metrics ----------

@register_metric_function
def exact_match(response: str, target: str):
    if response.lower() == target.lower():
        return 1.0, f"exact match: {response} == {target}"
    return 0.0, f"exact mismatch: {response} != {target}"


@register_metric_function
def url_match(response: str, target: str):
    pat = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
    r_urls = [urlparse(u).netloc for u in pat.findall(response)]
    t_urls = [urlparse(u).netloc for u in pat.findall(target)]
    if set(r_urls) == set(t_urls):
        return 1.0, "url match"
    return 0.0, f"url mismatch: {r_urls} vs {t_urls}"


@register_metric_function
def in_match(response: str, target: str):
    if response in target:
        return 1.0, "in target"
    return 0.0, "not in target"


@register_metric_function
def number_near(response: str, target: str, criterion: float):
    def _to_num(s):
        s = str(s)
        if "%" in s:
            try:
                return float(s.replace("%", "")) / 100.0
            except (ValueError, TypeError):
                return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    rn, tn = _to_num(response), _to_num(target)
    if rn is None or tn is None:
        if rn is None and tn is None and response == target:
            return 1.0, "string equal fallback"
        return 0.0, f"non-numeric: {rn}, {tn}"
    if abs(rn - tn) <= abs(tn) * criterion:
        return 1.0, f"near within {criterion*100}%"
    return 0.0, f"not near: {rn} vs {tn}"


@register_metric_function
def date_near(response: str, target: str):
    try:
        rd = dateparser.parse(str(response), settings={"PREFER_DAY_OF_MONTH": "first"})
    except Exception:
        rd = None
    try:
        td = dateparser.parse(str(target), settings={"PREFER_DAY_OF_MONTH": "first"})
    except Exception:
        td = None
    if rd is None or td is None:
        if rd is None and td is None:
            return 1.0, "both unparseable -> equal"
        return 0.0, "one side unparseable"
    if abs((rd - td).days) <= 31:
        return 1.0, f"date near: {rd} vs {td}"
    return 0.0, f"date far: {rd} vs {td}"


# ---------- LLM-driven alignment ----------

primary_key_preprocess_prompt = """Your task is to align two vocabularies. The inputs are the vocabulary to be aligned and the reference vocabulary respectively. Note that you need to perform semantic alignment (not positional alignment). If two strings are exactly the same, they must correspond to each other. These two strings are supposed to represent the same entity, with differences only in the expression forms and formats.


The vocabulary to be aligned is as follows:
{response}

The reference vocabulary is as follows:
{reference}

The alignment rules are as follows:
List the values in the vocabulary to be aligned one by one. If there is a value in the reference vocabulary that has the same meaning as this value, `transform` should be represented as the value from the reference vocabulary; otherwise, `transform` should be represented as the original value from the vocabulary to be aligned.

Note that `origin` must be taken from the vocabulary to be aligned keeping the original format, and `transform` must be taken from the reference vocabulary. For example: Some words in the vocabulary to be aligned might be the words in the reference vocabulary with Markdown formatting added, keep the to be aligned format in `origin` and the reference format in `transform`.

For the `origin`, first find the `transform` that is the closest in meaning and then judge whether they correspond to each other. Those entities not correspond to each other could not output.

Please output the alignment results in the following format:
```json
{{
    "origin_str1": "transform_str1",
    "origin_str2": "transform_str2"
}}
```
"""


def parse_markdown_json(completion: str) -> Optional[dict]:
    matches = re.findall(r"```json\s*(\{.*?\})\s*```", completion, re.DOTALL)
    if not matches:
        # also try bare JSON
        try:
            return json.loads(completion.strip())
        except Exception:
            return None
    try:
        return json.loads(matches[-1])
    except Exception:
        return None


# Regex fallback for the eval_column_prompt output shape.
# Matches lines like ``"idx_3": 1`` / ``idx_12: 0`` anywhere in the text,
# rescuing scores when the LLM emits valid item-by-item judgements but
# fails to wrap them in a fenced JSON block (or truncates mid-block).
_IDX_SCORE_RE = re.compile(r'"?idx_(\d+)"?\s*:\s*([01])\b')


def _regex_scrape_scores(completion: str) -> Optional[dict]:
    if not completion:
        return None
    out: dict[str, int] = {}
    for m in _IDX_SCORE_RE.finditer(completion):
        out[f"idx_{m.group(1)}"] = int(m.group(2))
    return out or None


def primary_key_preprocess(response: list, reference: list, model_config_name: str):
    out = {}
    result = llm_completion(
        messages=primary_key_preprocess_prompt.format(response=response, reference=reference),
        model_config_name=model_config_name,
    )
    if result is None or result.content is None:
        return out
    try:
        m = parse_markdown_json(result.content)
        if m:
            out.update(m)
    except Exception:
        pass
    return out


eval_column_prompt = """You are an expert in grading answers. Your task is to score the responses to a certain question. Below, you will be provided with a set of standard answers, a set of responses to be graded, and specific grading criteria.

Each answer and each response has an idx. Please score each pair of answers and responses in this set according to the following methods:
1. The scoring range is from 0 to 1. A score of 1 indicates a completely correct answer. For deduction items, please refer to the specific grading criteria section.
2. After reading the standard answers, responses to be graded, and grading criteria, please first analyze and judge them item by item according to the grading criteria.
3. The score can only be an integer of 0 or 1.
4. After the analysis and judgment, please provide the final scoring results. Each pair should have a score. Output in Markdown JSON format, as shown below:
```json
{{
    "idx_xxx": score,
    "idx_yyy": score,
    ...
}}
```

====== criterion-start ======
{criterion}
====== criterion-end ======

====== response-start ======
{response}
====== response-end ======

Now start scoring. Please make sure to analyze each item step by step before providing the final scoring results.

"""


@register_metric_function
def llm_judge(response, target, criterion, model_config_name="default_eval_config"):
    # Per-row llm_judge unused in column-batched pipeline.
    return None, None


_JUDGE_CHUNK_SIZE = 20
_JUDGE_MAX_RETRIES = 2
# Chunks within a column are independent; judge them concurrently.
# Cap via env to respect judge-side rate limits.
_JUDGE_MAX_WORKERS = int(os.getenv("WS_JUDGE_WORKERS", "8"))


def _judge_one_chunk(
    chunk_resp: List[str],
    chunk_tar: List[str],
    criterion: str,
    model_config_name: str,
) -> tuple[list[Optional[int]], list[str]]:
    """One judge call for up to ``_JUDGE_CHUNK_SIZE`` items, with retries.

    Returns ``(scores, msgs)`` per item. ``scores[i]`` is ``None`` for
    items the judge could not score after retries — callers decide how
    to handle (vs. silently defaulting to 0).
    """
    response_dict = {
        f"idx_{i}": {"response": r, "target": t}
        for i, (r, t) in enumerate(zip(chunk_resp, chunk_tar))
    }
    prompt = eval_column_prompt.format(criterion=criterion, response=response_dict)

    last_reason = ""
    for attempt in range(_JUDGE_MAX_RETRIES + 1):
        result = llm_completion(messages=prompt, model_config_name=model_config_name)
        if result is None or result.content is None:
            last_reason = "empty"
            continue
        score_dict = parse_markdown_json(result.content) or _regex_scrape_scores(result.content)
        if not score_dict:
            last_reason = "parse_error"
            continue
        scores: list[Optional[int]] = []
        missing = 0
        for i in range(len(chunk_resp)):
            v = score_dict.get(f"idx_{i}")
            if v is None:
                scores.append(None)
                missing += 1
            else:
                try:
                    scores.append(int(v))
                except Exception:
                    scores.append(None)
                    missing += 1
        # If most are missing, treat as parse failure and retry; if just
        # a few are missing, accept the partial result and move on.
        if missing > max(1, len(chunk_resp) // 2):
            last_reason = f"partial({missing}/{len(chunk_resp)} missing)"
            continue
        msg_head = (result.content or "")[:200]
        msgs = [msg_head] * len(chunk_resp)
        if missing:
            logger.warning(
                "llm_judge_column: chunk had %d/%d unparseable idx; kept partial.",
                missing, len(chunk_resp),
            )
        return scores, msgs

    logger.warning(
        "llm_judge_column: chunk of %d items failed after %d retries (%s); "
        "scoring None and downstream will treat as judge_unavailable.",
        len(chunk_resp), _JUDGE_MAX_RETRIES + 1, last_reason,
    )
    return [None] * len(chunk_resp), [f"llm judge failed: {last_reason}"] * len(chunk_resp)


@register_metric_function
def llm_judge_column(
    response: List[str],
    target: List[str],
    criterion: str,
    model_config_name: str,
):
    """Score (response, target) pairs by LLM judge.

    Robustness:
    - Splits into chunks of ``_JUDGE_CHUNK_SIZE`` to bound output length.
    - Retries each chunk up to ``_JUDGE_MAX_RETRIES`` on empty/parse failures.
    - Falls back to a regex scrape when fenced JSON is malformed.
    - Returns 0 (not None) for items the judge ultimately could not score,
      but logs a column-level warning so the run is flagged for re-grading.
    """
    n = len(response)
    if n == 0:
        return [], []

    starts = list(range(0, n, _JUDGE_CHUNK_SIZE))

    def _run(start: int):
        end = min(start + _JUDGE_CHUNK_SIZE, n)
        return _judge_one_chunk(
            response[start:end], target[start:end], criterion, model_config_name,
        )

    if len(starts) <= 1 or _JUDGE_MAX_WORKERS <= 1:
        results = [_run(s) for s in starts]
    else:
        workers = min(_JUDGE_MAX_WORKERS, len(starts))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            # map preserves input order, so chunks reassemble correctly.
            results = list(ex.map(_run, starts))

    all_scores: list[Optional[int]] = []
    all_msgs: list[str] = []
    for s, m in results:
        all_scores.extend(s)
        all_msgs.extend(m)

    unavailable = sum(1 for s in all_scores if s is None)
    if unavailable:
        logger.warning(
            "llm_judge_column: %d/%d items unavailable after retries — "
            "scoring those as 0. Consider re-grading this column.",
            unavailable, n,
        )
    final_scores = [int(s) if s is not None else 0 for s in all_scores]
    return final_scores, all_msgs
