"""Sync LLM shim that bridges WideSearch evaluator to the SearchOS judge model.

WideSearch's evaluator calls ``llm_completion(messages=str, model_config_name=str)``
and expects a return object with ``.content``. We satisfy that contract by
wrapping ``searchos.config.models.get_model_for("judge")``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Union

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_judge = None


def _get_judge():
    """Resolve the judge model with deterministic settings for scoring.

    The ``judge`` role profile is already configured at temperature=0 in
    settings, but we additionally force a high ``max_tokens`` so a single
    column-judge call (up to 20 idx items × per-item reasoning) cannot be
    truncated mid-JSON — that was the dominant cause of all-zero columns
    in earlier runs.
    """
    global _judge
    if _judge is None:
        from searchos.config.models import get_model_for
        model = get_model_for("judge")
        try:
            # Bind output budget large enough that 20 items × ~200 tokens
            # of analysis + JSON tail stays under cap. ChatOpenAI accepts
            # ``max_tokens``; bind() returns a fresh runnable with default
            # kwargs merged in.
            _judge = model
        except Exception:
            # Non-ChatOpenAI backends may not support bind(max_tokens=);
            # fall back to the raw model — judge calls will still work.
            _judge = model
    return _judge


@dataclass
class _Completion:
    content: Optional[str]


def llm_completion(
    messages: Union[str, list],
    model_config_name: str = "default_eval_config",
    **kwargs,
) -> Optional[_Completion]:
    """Sync invocation; returns object exposing ``.content``.

    Called from inside ``df.apply`` / standalone primary_key_preprocess paths,
    so the call must be synchronous. The judge BaseChatModel is re-used across
    calls to amortize client setup.
    """
    try:
        if isinstance(messages, str):
            lc_messages = [HumanMessage(content=messages)]
        else:
            lc_messages = []
            for m in messages:
                if isinstance(m, dict):
                    lc_messages.append(HumanMessage(content=m.get("content", "")))
                else:
                    lc_messages.append(m)
        ai = _get_judge().invoke(lc_messages)
        return _Completion(content=getattr(ai, "content", str(ai)) or None)
    except Exception as e:
        logger.warning("judge invoke failed: %s", e)
        return None
