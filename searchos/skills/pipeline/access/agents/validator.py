"""独立验收 Agent：执行候选、核对语义和提交结论。"""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from searchos.skills.pipeline.access.agents.prompts.validator import SYSTEM_PROMPT
from searchos.skills.pipeline.access.session import (
    FINALIZATION_ATTEMPTS,
    MAX_REPAIR_TURNS,
    budget_signal,
    closing_tool_error,
    final_instruction,
    prepare_messages_async,
    tool_protocol_error,
)
from searchos.skills.pipeline.access.tools.execute import VALIDATOR_EXEC_TOOL as EXEC_TOOL
from searchos.skills.pipeline.access.tools.files import READ_FILE_TOOL
from searchos.skills.pipeline.access.validation.checks import (
    validate_execution_result,
)
from searchos.skills.pipeline.access.validation.progress import (
    ValidationReview,
)

_TOOLS = {"read_file", "exec", "send_message"}


def _output_identity(work_dir, output):
    relative = Path(output)
    if not output or relative.is_absolute() or ".." in relative.parts:
        return None
    path = work_dir / relative
    try:
        if (not path.resolve().is_relative_to(work_dir.resolve())
                or any((work_dir / Path(*relative.parts[:index])).is_symlink()
                       for index in range(1, len(relative.parts) + 1))):
            return None
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    except OSError:
        return None


class ValidationAgent:
    def __init__(self, model, workspace, record, *, host, notes, on_stage=None, max_turns=50):
        if max_turns < 1:
            raise ValueError("validation max_turns must be positive")
        self.model, self.workspace, self.record = model, workspace, record
        self.host, self.notes = host, notes
        self.on_stage, self.max_turns = on_stage, max_turns
        self.review = ValidationReview(record, workspace.validation.checkpoint_validation_progress)
        self.calls, self.sessions = 0, 0
        self.usage: dict[str, int] = {}

    @property
    def state(self):
        return self.review.state

    @property
    def path(self):
        return self.review.path

    def snapshot(self):
        """返回恢复用的独立副本，调用方不能修改运行中的验收会话。"""
        return deepcopy(self.review.state)

    def progress(self):
        return self.review.progress() if 'examples' in self.review.state else {}


    async def _tool(self, name, args):
        if name not in _TOOLS:
            raise ValueError("validation tools are limited to read_file, exec and send_message")
        if name == "send_message":
            role, content = args.get("role"), args.get("content")
            if role == "builder":
                return self.review.submit(content)
            if role != "planner" or not isinstance(content, dict):
                raise ValueError("send_message requires role builder or planner and object content")
            return await self.workspace.send_message(role, content, sender="validator")
        if name == "read_file":
            return await self.workspace.package.read_candidate(
                self.candidate_dir, work_dir=self.workspace.executor.work_dir, **args)
        capability = args.get("capability_id")
        if capability is not None and capability not in self.review.capabilities():
            raise ValueError("exec capability_id must identify an existing capability")
        if args.get("argv") is not None and capability is None:
            raise ValueError("candidate CLI argv execution requires capability_id")
        if args.get("check_kind", "positive") not in {"positive", "boundary"}:
            raise ValueError("exec check_kind must be positive or boundary")
        if args.get("expected_status", "ok") not in {"ok", "empty", "invalid_input"}:
            raise ValueError("exec expected_status must be ok, empty or invalid_input")
        business = args.get("argv") is not None and not {"--help", "-h"}.intersection(args["argv"])
        example = self.review.execution_example(args) if business else None
        work = self.workspace.executor.work_dir or self.workspace.runtime_dir / "work"
        before = _output_identity(work, example.get("output", "")) if example else None
        result = await self.workspace.executor.execute(**{key: value for key, value in args.items()
            if key not in {"capability_id", "check_kind", "expected_status"}},
            package_dir=self.candidate_dir, trace_functions=business)
        if example is not None:
            if before is not None and before == _output_identity(work, example.get("output", "")):
                result["output_unchanged"] = True
            index = max((case["example"] for case in self.review.state["case_results"]), default=-1) + 1
            result["validation"] = validate_execution_result(example, result,
                work_dir=Path(result.get("work_dir") or self.workspace.executor.work_dir
                              or self.workspace.runtime_dir / "work"),
                execution_dir=self.workspace.runtime_dir / "executions",
                artifact_store=self.workspace.package.result_store, example_index=index)
        return result


    def _finish(self, *, error=""):
        result = self.review.result(error=error)
        self.review.state["capability_results"] = deepcopy(result["capability_results"])
        self.review.state["result"] = result
        self.review.save()
        self.record.event("access_validation_completed", report=result)
        return result

    async def validate(self, *, candidate_dir, candidate_version, deterministic, plan=None, examples=None,
                       resume=None, function_index=None, validation_scope=None, previous_report=None) -> dict:
        self.candidate_dir = Path(candidate_dir).resolve()
        self.sessions += 1
        gate = self.review.start(candidate_dir=self.candidate_dir, candidate_version=candidate_version,
            deterministic=deterministic, host=self.host, notes=self.notes, plan=plan, examples=examples,
            resume=resume, function_index=function_index, validation_scope=validation_scope,
            previous_report=previous_report)
        if self.on_stage is not None:
            await self.on_stage("access_validation")
        if not deterministic.get("package_valid"):
            return self._finish()
        definitions = [deepcopy(READ_FILE_TOOL), deepcopy(EXEC_TOOL), deepcopy(SEND_MESSAGE_TOOL)]
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=json.dumps({
            "host": self.host, "user_need": self.notes, "plan": plan,
            "candidate_version": candidate_version, "package_files": self.review.state["files"],
            "suggested_examples": self.review.state["examples"],
            "function_index": self.workspace.package.result_store.present(function_index) if function_index else None,
            "validation_scope": validation_scope,
            "builder_budget": deepcopy(getattr(self.workspace, 'builder_budget', {})),
            "max_repair_turns": MAX_REPAIR_TURNS,
            "previous_regression_commands": self.review.previous_regression_commands,
            "accepted_checks": self.review.state.get("accepted_checks", []),
            "package_validation": self.workspace.package.result_store.present(gate),
        }, ensure_ascii=False))]
        last_error = ""
        try:
            model = self.model.bind_tools(definitions)
            call_limit = self.max_turns + 1 + FINALIZATION_ATTEMPTS
            for turn in range(call_limit):
                closing = turn >= self.max_turns + 1
                messages = await prepare_messages_async(
                    messages, self.workspace, role="validator", model=self.model)
                phase = "finalization" if closing else "supplemental" if turn >= self.max_turns else "verification"
                signal = budget_signal('validator', call=turn + 1, call_limit=call_limit, phase=phase,
                    phase_limit=call_limit if closing else self.max_turns + 1 if turn >= self.max_turns else self.max_turns)
                self.review.state["budget"] = signal
                messages.append(HumanMessage(content=json.dumps({
                    "validation_call": turn + 1, "call_limit": call_limit,
                    "budget": signal,
                    "instruction": (final_instruction('validator') if closing else
                                    "修正调用：按回执补跑缺失 CLI、读取结果并提交结论；可在一次响应依次调用 exec 和 send_message。"
                                    if turn >= self.max_turns else
                                    "先补跑 pending_regressions 原命令与预期，再补正常业务 CLI；核对语义后提交结论。"),
                    "progress": self.workspace.package.result_store.present(self.review.progress()),
                }, ensure_ascii=False)))
                self.review.state["calls"] += 1
                self.calls += 1
                self.review.save()
                try:
                    response = await model.ainvoke(messages)
                except Exception as exc:
                    if not closing or not tool_protocol_error(exc):
                        raise
                    last_error = f"tool_protocol_error: {exc}"
                    self.review.state.setdefault("report_errors", []).append(last_error)
                    self.review.save()
                    self.record.event('agent_tool_protocol_rejected', role='validator', turn=turn + 1,
                                      error=self.record.clean(str(exc)))
                    messages.append(HumanMessage(content='网关拒绝了工具调用。' + final_instruction('validator')))
                    continue
                calls = getattr(response, "tool_calls", None) or []
                usage = getattr(response, "usage_metadata", None) or {}
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    if isinstance(usage.get(key), int):
                        self.review.state["usage"][key] = self.review.state["usage"].get(key, 0) + usage[key]
                        self.usage[key] = self.usage.get(key, 0) + usage[key]
                self.review.state["responses"].append({"content": response.content, "tool_calls": calls, "usage": usage})
                self.review.save()
                self.record.event("access_validation_response", turn=turn + 1, content=response.content,
                                  tool_calls=calls, usage=usage)
                messages.append(response)
                if not calls:
                    last_error = "请通过 send_message(role=builder, content={checks: [...]}) 提交逐能力结论。"
                    messages.append(HumanMessage(content=last_error))
                    continue
                submitted = False
                for call in calls:
                    args = {}
                    try:
                        args = call.get("args") or {}
                        if isinstance(args, str):
                            args = json.loads(args)
                        if not isinstance(args, dict):
                            raise ValueError("tool args must be an object")
                        blocked = closing_tool_error('validator', call) if closing else None
                        result = blocked or await self._tool(call["name"], args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                        self.review.state.setdefault("report_errors", []).append(str(exc))
                    submitted |= (call["name"] == "send_message" and isinstance(args, dict)
                                  and args.get("role") == "builder" and not result.get("error"))
                    shown = self.review.observe(call["name"], args if isinstance(args, dict) else {}, result)
                    if call["name"] != "read_file":
                        shown = self.workspace.package.result_store.present(shown)
                    messages.append(ToolMessage(content=json.dumps(shown, ensure_ascii=False, default=str),
                                                tool_call_id=call["id"]))
                if submitted and self.review.state.get("report_complete"):
                    return self._finish()
                last_error = "请根据 send_message 回执修正待提交能力；已接收结论会保留。"
        except asyncio.CancelledError:
            result = self.review.result()
            result.update(cancelled=True, valid=False, report_complete=False)
            self.review.state.update(cancelled=True, result=result)
            self.review.save()
            raise
        except Exception as exc:
            return self._finish(error=f"validation_model_error: {type(exc).__name__}: {exc}")
        return self._finish(error="validation_report_unavailable: " + (last_error or "验证调用额度耗尽。"))


SEND_MESSAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": (
            "Send {checks: [...], repair_budget: {max_turns: 20, reason: 'repair work'}} to builder "
            "to submit capability verdicts. For failures or unfinished checks, specify 1–50 Builder "
            "LLM calls for reading, investigation, fixes, testing and resubmission. "
            "Or send a question "
            "to planner to clarify the locked requirements. Checks use capability_id, status "
            "(passed/failed/uncertain), reason and intent_question when needed. The host attaches "
            "real CLI executions from this candidate session."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["builder", "planner"]},
                "content": {"type": "object", "description":
                    "Builder reports contain checks and, when repair is needed, repair_budget with "
                    "max_turns (integer 1–50) and reason (1–1000 characters). Planner questions use question/capability_id."},
            },
            "required": ["role", "content"],
            "additionalProperties": False,
        },
    },
}
