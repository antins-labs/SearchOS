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
from searchos.skills.pipeline.access.tools.network import NETWORK_CHECK_TOOL, check_network
from searchos.skills.pipeline.access.tools.files import READ_FILE_TOOL
from searchos.skills.pipeline.access.validation.checks import (
    validate_execution_result,
)
from searchos.skills.pipeline.access.validation.progress import (
    ValidationReview, identity,
)

_TOOLS = {"read_file", "exec", "send_message", "network_check"}


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
        if name == 'network_check':
            return await check_network(**args)
        if name not in _TOOLS:
            raise ValueError("validation tools are limited to read_file, exec, network_check and send_message")
        if name == "send_message":
            role, content = args.get("role"), args.get("content")
            if role == "builder":
                return self.review.submit(content, bind_execution=self._bind_execution)
            if role != "planner" or not isinstance(content, dict):
                raise ValueError("send_message requires role builder or planner and object content")
            return await self.workspace.send_message(role, content, sender="validator")
        if name == "read_file":
            return await self.workspace.package.read_candidate(
                self.candidate_dir, work_dir=self.workspace.executor.work_dir, **args)
        result = await self.workspace.executor.execute(**args, package_dir=self.candidate_dir,
            trace_functions=True, browser_request={'role': 'validator', **args})
        return {**result, 'candidate_version': self.review.state['candidate_version']}

    def _bind_execution(self, capability, reference):
        """报告引用本轮已保存执行；检查冻结产物，不重跑命令。"""
        if (not isinstance(reference, dict) or not isinstance(reference.get('execution_id'), str)
                or set(reference) - {'execution_id', 'output', 'regression_of', 'check_kind', 'expected_status'}):
            raise ValueError('executions require execution_id and optional output/regression_of/check_kind/expected_status')
        observation = next((item for item in self.review.state['observations']
            if item['tool'] == 'exec' and item['result'].get('execution_id') == reference['execution_id']), None)
        if observation is None or observation['result'].get('candidate_version') != self.review.state['candidate_version']:
            raise ValueError('execution_id must reference a real execution of this candidate session')
        newer = self.review.state['observations'][self.review.state['observations'].index(observation) + 1:]
        if any(item['tool'] == 'exec' and item['result'].get('execution_id')
               and item['result'].get('started') is not False
               and identity(item['args'])[1:] == identity(observation['args'])[1:] for item in newer):
            raise ValueError('execution was superseded; cite the latest execution of this input')
        args, result = observation['args'], deepcopy(observation['result'])
        selected = self.review.execution_example({**args, 'capability_id': capability,
            **{key: value for key, value in reference.items() if key != 'execution_id'}})
        execution_root = self.workspace.runtime_dir / 'executions'
        output = selected.get('output', '')
        if output:
            result['output_unchanged'] = output not in result.get('updated_files', [])
        case = validate_execution_result(selected, result,
            work_dir=execution_root / reference['execution_id'] / 'artifacts',
            execution_dir=execution_root, artifact_store=self.workspace.package.result_store,
            example_index=len(self.review.state['case_results']),
            check_records=self.review.state.get('examples_locked', False),
            check_json=self.review.state.get('examples_locked', False) or 'output' in reference)
        case.update(observation_id=observation['id'], candidate_version=self.review.state['candidate_version'])
        return case


    def _finish(self, *, error=""):
        result = self.review.result(error=error)
        if result.get('valid'):
            from searchos.network import current_context
            accepted = {eid for check in self.review.state.get('accepted_checks', [])
                        if check['status'] == 'passed' for eid in check.get('execution_ids', [])}
            verified = {eid for cap in result['capability_results']
                        for eid, _ in self.review._execution_evidence(cap, successful=True)
                        if eid in accepted}
            current_context().confirm_connections([
                item['result'].get('network', {}) for item in self.review.state['observations']
                if item['tool'] == 'exec' and item['result'].get('execution_id') in verified
            ])
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
            previous_report=previous_report, examples_locked=self.workspace.validation.examples_locked)
        if self.on_stage is not None:
            await self.on_stage("access_validation")
        if not deterministic.get("package_valid"):
            return self._finish()
        definitions = [deepcopy(READ_FILE_TOOL), deepcopy(EXEC_TOOL), deepcopy(SEND_MESSAGE_TOOL),
                       deepcopy(NETWORK_CHECK_TOOL)]
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=json.dumps({
            "host": self.host, "user_need": self.notes, "plan": plan,
            "research_observations": self.workspace.package.result_store.present(
                self.workspace.site_intent.state.get('observations', [])) if self.workspace.site_intent else [],
            "candidate_version": candidate_version, "package_files": self.review.state["files"],
            "host_examples": self.review.state["examples"],
            "function_index": self.workspace.package.result_store.present(function_index) if function_index else None,
            "validation_scope": validation_scope,
            "builder_budget": deepcopy(getattr(self.workspace, 'builder_budget', {})),
            "max_repair_turns": MAX_REPAIR_TURNS,
            "previous_regression_commands": self.review.previous_regression_commands,
            "accepted_checks": self.review.state.get("accepted_checks", []),
            "package_validation": self.workspace.package.result_store.present(gate),
        }, ensure_ascii=False))]
        if original := getattr(self, 'resume_input', None):
            result = await self._tool('exec', original)
            shown = self.review.observe('exec', original, result)
            self.resume_input = None
            messages.append(HumanMessage(content=f"""已独立重放中断前的原输入：{json.dumps(self.workspace.package.result_store.present(shown), ensure_ascii=False)}"""))
            progress = self.review.progress()
            if progress.get('wait_external') and not progress['pending_capabilities'] and not progress['pending_regressions']:
                return self._finish()
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
                                    """按回执补齐执行或证据引用，读取结果并提交结论；可在一次响应依次调用 exec 和 send_message。"""
                                    if turn >= self.max_turns else
                                    """先复验 pending_regressions 原业务输入，再用区别于 Builder 自测和文档示例的新业务输入补齐待验能力；固定输入范围说明限制，核对语义后在报告中写明输入差异并引用真实执行。"""),
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
                    messages.append(HumanMessage(content=f"""网关拒绝了工具调用。{final_instruction('validator')}"""))
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
                                  reasoning=(getattr(response, 'additional_kwargs', {}) or {}).get('reasoning_content'),
                                  tool_calls=calls, usage=usage)
                messages.append(response)
                if not calls:
                    last_error = """请通过 send_message(role=builder, content={checks: [...]}) 提交逐能力结论。"""
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
                    self.record.event('agent_tool_result', role='validator', name=call.get('name'),
                                      call_id=call.get('id'), content=shown)
                    messages.append(ToolMessage(content=json.dumps(shown, ensure_ascii=False, default=str),
                                                tool_call_id=call["id"]))
                if submitted and self.review.state.get("report_complete"):
                    return self._finish()
                progress = self.review.progress()
                if progress.get('wait_external') and not progress['pending_capabilities'] and not progress['pending_regressions']:
                    return self._finish()
                last_error = """请根据 send_message 回执修正待提交能力；已接收结论会保留。"""
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
        "description": "Submit capability checks to the builder and receive a receipt, or ask the planner "
                       "to clarify business scope or research evidence.",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["builder", "planner"],
                         "description": "Send capability verdicts to builder or scope questions to planner."},
                "content": {"type": "object", "description": (
                    "For builder, supply checks and, for failed or unfinished work, a repair budget. "
                    "Example shape: {checks: [...], repair_budget: {max_turns: 20, reason: 'repair work'}}. "
                    "Allow 1–50 builder calls to investigate, fix, test and resubmit. Give a 1–1000 character reason. "
                    "Each check includes capability_id, status (passed, failed or uncertain), reason and executions. "
                    "Put ordinary invalid inputs, error classification and exploratory boundary observations in "
                    "optional warnings (an array of strings). An uncertain check can include intent_question. "
                    "For passed and failed, cite actual business execution from this candidate session. "
                    "Each execution reference takes execution_id and optional output, regression_of, check_kind and "
                    "expected_status. Set output to a work-relative JSON file or an empty string for JSON stdout. "
                    "Omit it for raw output and assertions. Read saved copies via stdout_file or saved_files. "
                    "Use regression_of to link a previous failure to a fresh equivalent execution. "
                    "For planner, send question and the relevant capability_id."
                )},
            },
            "required": ["role", "content"],
            "additionalProperties": False,
        },
    },
}
