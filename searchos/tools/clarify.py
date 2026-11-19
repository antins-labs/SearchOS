"""Orchestrator 专用的结构化澄清。Search、Explore 与 Local QA 不注册此工具。"""

from __future__ import annotations

import json
from typing import Annotated

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from searchos.agents.runtime import _ctx
from searchos.harness.clarify import ClarifyInvalid


class ClarifyQuestion(BaseModel):
    """一题。选项写清选择后的后果，用户还可以补充文字。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1, max_length=60,
        description="Unique id for this question within the call.",
    )
    prompt: str = Field(min_length=1, max_length=240, description="The question shown to the user.")
    options: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=2, max_length=5,
        description="Two to five choices. State the consequence of each choice.",
    )
    allowMultiple: bool = Field(description="True when the user may select more than one option.")


class AskUserQuestionInput(BaseModel):
    """一次只问阻塞交付的关键分叉，1–3 题。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[ClarifyQuestion] = Field(
        min_length=1, max_length=3,
        description="One to three questions. Call this tool alone and wait for the answers.",
    )


@tool(args_schema=AskUserQuestionInput)
async def AskUserQuestion(questions: list[ClarifyQuestion]) -> str:
    """Ask the user a blocking clarification and wait for the structured answer.

    Use this only when a missing user decision changes the research scope, source
    mode, delivery policy, or an irreversible preference. If the scope, columns,
    and missing-value rule are already clear, deliver the work instead of asking.
    Call this tool by itself. Each question has 2–5 options and may allow multiple
    selections; the user can also add custom text. Do not repeat a question already
    answered, and do not turn this into a questionnaire.

    The tool returns {"answers":[{"id","selected","custom?"}]}.
    Example: {"questions":[{"id":"delivery","prompt":"How should the table be delivered?",
    "options":["Deliver the full table now and write / for unknown cells",
    "Fill the missing attributes before delivery"],"allowMultiple":false}]}
    """
    gate = _ctx.clarify_gate
    if gate is None:
        return json.dumps({
            "error": "AskUserQuestion is unavailable. Deliver with the current evidence.",
        }, ensure_ascii=False)
    try:
        result = await gate.ask([item.model_dump() for item in questions])
    except ClarifyInvalid as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
