"""ControlMiddleware — the plan §3.1 single-seam control layer.

Composes the two historically-separate control responsibilities into
one middleware so spawn code adds ONE middleware instead of picking
``LayeredContextMiddleware`` vs ``DynamicTrimMiddleware`` each time:

1. Context compression — delegates to ``LayeredContextMiddleware`` when
   ``SF_USE_LAYERED_CONTEXT=1`` is set, otherwise falls back to the
   cheaper ``DynamicTrimMiddleware``.
2. Skill injection — optional strategy-skill prompt fragments (plan §6)
   folded into the system prompt via a caller-supplied
   ``skill_prompt_provider`` callable. The callable receives the current
   agent id and returns a text block (or empty string). This keeps the
   actual skill matching in the orchestrator / skill registry while the
   middleware just stitches the text in.

Prompt assembly (SOCM snapshot + instruction) stays in
``orchestrator_tools._spawn_sub_agent`` where the state is — Control
runs AFTER prompt is built.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.context.dynamic_trim import DynamicTrimMiddleware
from searchos.harness.middleware.context.layered_context import LayeredContextMiddleware


SkillPromptProvider = Callable[[str], str]


class ControlMiddleware(AgentMiddleware):
    """Single-seam Control layer (plan §3.1).

    Picks the right context strategy and layers optional skill-prompt
    injection on top of it.
    """

    _inner: AgentMiddleware
    _skill_prompt_provider: SkillPromptProvider | None

    def __init__(
        self,
        *,
        judge_model: Any = None,
        workspace: Any = None,
        layer1_max_tokens: int = 40000,
        layer2_max_tokens: int = 8000,
        layer3_max_tokens: int = 2000,
        trim_max_tokens_fraction: float = 0.85,
        trim_max_tokens: int | None = None,
        skill_prompt_provider: SkillPromptProvider | None = None,
        force_layered: bool | None = None,
    ) -> None:
        # Decide the inner strategy. ``force_layered`` lets tests pin
        # either path; production defaults to the env flag.
        if force_layered is None:
            use_layered = os.getenv("SF_USE_LAYERED_CONTEXT", "0") == "1"
        else:
            use_layered = force_layered

        if use_layered and judge_model is not None:
            inner: AgentMiddleware = LayeredContextMiddleware(
                judge_model=judge_model,
                workspace=workspace,
                layer1_max_tokens=layer1_max_tokens,
                layer2_max_tokens=layer2_max_tokens,
                layer3_max_tokens=layer3_max_tokens,
            )
        else:
            trim_kwargs: dict[str, Any] = {}
            if trim_max_tokens is not None:
                trim_kwargs["max_tokens"] = trim_max_tokens
            else:
                trim_kwargs["max_tokens_fraction"] = trim_max_tokens_fraction
            inner = DynamicTrimMiddleware(**trim_kwargs)
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_skill_prompt_provider", skill_prompt_provider)

    # ---- before_model: inject skills, then defer to inner ----
    def before_model(self, state: Any, runtime: Any = None):  # type: ignore[override]
        from searchos.config.settings import settings
        provider = self._skill_prompt_provider
        if provider is not None and settings.enable_skills:
            try:
                agent_id = getattr(runtime, "thread_id", "") or ""
                fragment = provider(agent_id)
            except Exception:
                fragment = ""
            if fragment:
                messages = list(getattr(state, "messages", None) or state.get("messages") or [])
                from langchain_core.messages import SystemMessage
                messages.insert(0, SystemMessage(content=f"[skills]\n{fragment}"))
                try:
                    state.messages = messages
                except Exception:
                    if isinstance(state, dict):
                        state["messages"] = messages
        if hasattr(self._inner, "before_model"):
            return self._inner.before_model(state, runtime)  # type: ignore[arg-type]
        return None

    # ---- Pass-through other hooks ----
    def after_model(self, state: Any, runtime: Any = None):  # type: ignore[override]
        if hasattr(self._inner, "after_model"):
            return self._inner.after_model(state, runtime)  # type: ignore[arg-type]
        return None

    def before_tool(self, state: Any, runtime: Any = None):  # type: ignore[override]
        if hasattr(self._inner, "before_tool"):
            return self._inner.before_tool(state, runtime)  # type: ignore[arg-type]
        return None

    def after_tool(self, state: Any, runtime: Any = None):  # type: ignore[override]
        if hasattr(self._inner, "after_tool"):
            return self._inner.after_tool(state, runtime)  # type: ignore[arg-type]
        return None
