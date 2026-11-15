"""Agent 会话：历史压缩、运行预算和收尾规则。"""
from __future__ import annotations

import asyncio
import json
import math
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from searchos.harness.middleware.context.core.history import (
    count_context_tokens,
    render_history,
    split_history,
    summarize_history,
)
from searchos.harness.middleware.context.utils.token_counts import model_input_limit
from searchos.skills.pipeline.access.artifacts import private_directory

MAX_CONTEXT_BYTES = 96_000


SUMMARY_TOKENS = 1800


MAX_SUMMARY_WINDOW = 32_000


def _value(message):
    return message.model_dump(mode='json') if hasattr(message, 'model_dump') else str(message)


def _size(messages):
    return len(json.dumps([_value(message) for message in messages], ensure_ascii=False).encode())


def _save_history(messages, workspace):
    root = private_directory(workspace.package.result_store.root)
    path = root / f'history-{uuid4().hex}.json'
    with path.open('x', encoding='utf-8') as handle:
        path.chmod(0o600)
        json.dump(workspace.package.result_store.clean([_value(message) for message in messages]),
                  handle, ensure_ascii=False, default=str)
    return str(path)


def _archive_messages(messages, workspace, *, role):
    history = _save_history(messages, workspace)
    system = messages[0] if messages and isinstance(messages[0], SystemMessage) else SystemMessage(content='继续当前角色任务。')
    if _size([system]) > 16_000:
        system = SystemMessage(content=str(system.content)[:3000]
            + '\n完整角色说明已保存：' + history)
    task = str(messages[1].content)[:4000] if len(messages) > 1 else ''
    checkpoint = {'history_file': history, **workspace.context_snapshot(role)}
    shown = workspace.package.result_store.present(checkpoint)
    note = HumanMessage(content='继续完成当前任务。完整输入和较早交互已保存，按需读取历史文件。\n'
        + task + '\n当前状态：\n' + json.dumps(shown, ensure_ascii=False))
    last_ai = next((index for index in range(len(messages) - 1, 1, -1)
                    if isinstance(messages[index], AIMessage)), len(messages))
    recent = messages[last_ai:]
    if _size([*recent]) > MAX_CONTEXT_BYTES // 2:
        recent = [HumanMessage(content='最近一轮工具调用及结果已完成并保存：' + history
                              + '。根据当前文件和验收状态继续；可分页核对该轮观察。')]
    result = [system, note, *recent]
    if _size(result) > MAX_CONTEXT_BYTES:
        directory = workspace.package.result_store.present({key: checkpoint[key] for key in
            ('research_observations', 'validation_progress', 'package_files', 'latest_validation') if key in checkpoint})
        result = [system, HumanMessage(content='继续当前任务。完整历史：' + history
                    + '\n当前任务开头：' + task + '\n当前进度：\n'
                    + json.dumps(directory, ensure_ascii=False))]
    return result, history


def _event(workspace, name, **data):
    if workspace.record:
        workspace.record.event(name, **data)


def _completed(messages, shown, workspace, *, role, history, strategy):
    _event(workspace, 'context_compacted', role=role, original_bytes=_size(messages),
        retained_bytes=_size(shown), history_file=history, retained_messages=len(shown) - 2,
        strategy=strategy)
    return shown


def prepare_messages(messages, workspace, *, role):
    """归档完整输入；保留完整 AI/Tool 轮次，超大单轮改用文件引用。"""
    if _size(messages) <= MAX_CONTEXT_BYTES:
        return messages
    shown, history = _archive_messages(messages, workspace, role=role)
    return _completed(messages, shown, workspace, role=role, history=history, strategy='archive')


async def prepare_messages_async(messages, workspace, *, role, model, timeout_s=60):
    """自动生成续接摘要；完整原文持久保存，摘要异常时保留归档后备。"""
    if _size(messages) <= MAX_CONTEXT_BYTES:
        return messages
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError('compaction timeout must be finite and positive')
    # 共用完整事务边界，避免拆开并行工具调用及其结果。
    prefix, recent = split_history(messages, MAX_CONTEXT_BYTES // 4, _size)
    prior = [message for message in recent if message.additional_kwargs.get('sf_kind') == 'context_compaction']
    recent = [message for message in recent if message not in prior]
    fallback, history = _archive_messages(messages, workspace, role=role)
    retained = [*fallback[:2], *recent]
    window = min(model_input_limit(model) or MAX_SUMMARY_WINDOW, MAX_SUMMARY_WINDOW)
    summary_tokens = min(SUMMARY_TOKENS, max(1, window // 10))
    input_budget = window - summary_tokens - max(64, min(1024, window // 10))
    calls, usage = 0, {}

    class SummaryModel:
        async def ainvoke(self, request):
            nonlocal calls
            calls += 1
            _event(workspace, 'context_compaction_request', role=role, call=calls,
                history_file=history, input_tokens_estimate=count_context_tokens(request))
            response = await model.ainvoke(request, config={'metadata': {
                'sf_operation': 'context_compaction', 'sf_role': role}})
            observed = getattr(response, 'usage_metadata', None) or {}
            for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                if isinstance(observed.get(key), int):
                    usage[key] = usage.get(key, 0) + observed[key]
            _event(workspace, 'context_compaction_response', role=role, call=calls,
                history_file=history, usage=observed)
            return response

    try:
        async with asyncio.timeout(timeout_s):
            summary = await summarize_history(SummaryModel(), render_history([*prefix, *prior]),
                render_history(retained), summary_tokens=summary_tokens, input_budget=input_budget)
        handoff = HumanMessage(content='历史续接摘要；按当前任务与宿主状态继续：\n' + summary,
            additional_kwargs={'sf_synthetic': True, 'sf_kind': 'context_compaction'})
        shown = [*retained[:2], handoff, *recent]
        if _size(shown) > MAX_CONTEXT_BYTES:
            shown = [*retained[:2], handoff]
        if _size(shown) > MAX_CONTEXT_BYTES:
            raise ValueError('compaction handoff exceeds retained context budget')
    except asyncio.CancelledError:
        _event(workspace, 'context_compaction_cancelled', role=role, history_file=history,
               calls=calls, usage=usage)
        raise
    except Exception as exc:
        _event(workspace, 'context_compaction_failed', role=role, history_file=history,
               calls=calls, usage=usage, error_type=type(exc).__name__)
        return _completed(messages, fallback, workspace, role=role, history=history,
                          strategy='archive_fallback')
    _event(workspace, 'context_compaction_summary', role=role, history_file=history,
           calls=calls, usage=usage, summary=summary)
    return _completed(messages, shown, workspace, role=role, history=history, strategy='semantic_handoff')


FINALIZATION_ATTEMPTS = 3


MAX_REPAIR_TURNS = 50


def validate_repair_budget(value):
    """Validator 明确提交修复轮数和原因，字段错误留在验收会话纠正。"""
    if (not isinstance(value, dict) or set(value) != {'max_turns', 'reason'}
            or type(value.get('max_turns')) is not int
            or not 1 <= value['max_turns'] <= MAX_REPAIR_TURNS
            or not isinstance(value.get('reason'), str) or not 1 <= len(value['reason'].strip()) <= 1000):
        raise ValueError('repair_budget requires max_turns (integer 1–50) and reason (1–1000 characters)')
    return {'max_turns': value['max_turns'], 'reason': value['reason'].strip()}


def budget_signal(role, *, call, call_limit, phase, phase_limit=None, total_limit=None):
    """剩余调用含即将开始的本次调用；阶段、当前额度和总上限分别显示。"""
    total_limit = call_limit if total_limit is None else total_limit
    phase_limit = call_limit if phase_limit is None else phase_limit
    return {'role': role, 'phase': phase, 'call': call, 'call_limit': call_limit,
            'remaining_calls': max(0, call_limit - call + 1),
            'phase_remaining_calls': max(0, phase_limit - call + 1),
            'total_call_limit': total_limit, 'total_remaining_calls': max(0, total_limit - call + 1)}


def final_instruction(role):
    return {
        'planner': '当前是最终整理阶段。仅根据已有观察直接输出符合契约的最终 JSON。'
                   '研究工具调用会被代码拦截；依据校验回执修正字段，未确认范围写入 limitations 或 guidance。',
        'builder': '根据静态预检和验收回执补齐包文件、元数据与入口，继续使用工具修复。'
                   '完成后使用 send_message(role="validator") 交验；失败回执返回本循环继续处理。'
                   '优先完成可交验的包，并说明剩余限制。',
        'validator': '当前是最终报告阶段。使用 send_message(role="builder", content={"checks":[...]}) '
                     '提交已有证据支持的逐能力结论，未完成范围填写 uncertain 并说明原因。'
                     '仍需修复或补验时，在 content 中附 repair_budget={"max_turns":轮数,"reason":"工作量依据"}，'
                     '轮数为整数 1–50；根据读取、探查、修改、自测和重交所需工作分配。'
                     '读取、执行及其他角色消息调用会被代码拦截；根据报告回执修正提交。',
    }[role]


def closing_tool_error(role, call):
    """在执行前检查工具和目标角色，返回可供模型纠正的拒绝回执。"""
    if role == 'builder':
        return None
    args = call.get('args') or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    recipient = {'validator': 'builder'}.get(role)
    if (recipient and call.get('name') == 'send_message'
            and isinstance(args, dict) and args.get('role') == recipient):
        return None
    return {'error': 'finalization_tool_blocked', 'instruction': final_instruction(role)}


def tool_protocol_error(error):
    """仅恢复网关明确报告的未知工具协议错误，保留其他故障的原处理。"""
    message = str(error).lower()
    status = getattr(error, 'status_code', None)
    return (status == 400 or '400' in message or type(error).__name__ == 'BadRequestError') and any(
        marker in message for marker in ('non-exist tool', 'non-existent tool', 'unknown tool',
                                        'tool is not defined', 'tool not found'))
