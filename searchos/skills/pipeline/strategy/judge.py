"""只向独立 Judge 提交子任务产出，隐藏候选策略和生成信息。"""
from __future__ import annotations
import json
import math
from typing import Any
from searchos.skills.pipeline.strategy.prompt import JUDGE_PROMPT


async def judge_subtask(subtask: str, outcome: dict, *, model: Any = None, record_writer=None) -> dict:
    if model is None:
        from searchos.config.models import get_model_for
        model = get_model_for('judge')
    payload = {'subtask': subtask, **{k: outcome[k] for k in ('answer', 'evidence', 'sources')}}
    if record_writer:
        record_writer("judge-input.json", payload)
    content = json.dumps(payload, ensure_ascii=False)
    from searchos.config.settings import settings
    if len(content) > settings.judge_max_input_chars:
        raise ValueError('subtask outputs exceed judge input limit')
    from langchain_core.messages import SystemMessage, HumanMessage
    response = await model.ainvoke([SystemMessage(content=JUDGE_PROMPT), HumanMessage(content=content)])
    raw = response.content if hasattr(response, 'content') else str(response)
    if isinstance(raw, list):
        raw = ''.join(b.get('text', '') if isinstance(b, dict) else str(b) for b in raw)
    raw = str(raw).strip()
    if record_writer:
        record_writer("judge-response.json", {"content": raw})
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    verdict = json.loads(raw)
    if not isinstance(verdict, dict) or any(type(verdict.get(k)) is not bool for k in ('answered', 'grounded')):
        raise ValueError('judge answered/grounded must be booleans')
    confidence = verdict.get('confidence')
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('judge confidence must be a finite number in 0..1')
    if not isinstance(verdict.get('reason'), str) or not verdict['reason'].strip():
        raise ValueError('judge must explain success or failure')
    if not isinstance(verdict.get('issues'), list) or not all(isinstance(v, str) for v in verdict['issues']):
        raise ValueError('judge issues must be a string list')
    return verdict
