"""从创建记录投影只读进度；页面只接收阶段、能力与操作摘要。"""
import json
from pathlib import Path


def _json(path, root):
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size > 16_000_000:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _events(path, root, *, tail_bytes=512_000):
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            return []
        with path.open('rb') as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - tail_bytes) if tail_bytes else 0)
            if tail_bytes and size > tail_bytes:
                handle.readline()
            lines = handle.read().decode('utf-8', errors='replace').splitlines()
        events = []
        for line in lines:
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    events.append(event)
            except ValueError:
                continue
        return events
    except OSError:
        return []


def _activity(event):
    kind = event.get('event')
    role = {'site_intent_response': 'planner', 'model_started': 'builder',
            'model_completed': 'builder', 'access_validation_response': 'validator'}.get(kind)
    action = {'site_plan_ready': ('planner', 'plan_ready'),
              'validation_preflight': ('validator', 'validation_started'),
              'validation_completed': ('validator', 'validation_finished'),
              'builder_repair_continued': ('builder', 'repair_started'),
              'artifact_saved': (None, 'draft_saved'), 'cancelled': (None, 'stopped')}.get(kind)
    if kind == 'role_message':
        target = event.get('role')
        action = (event.get('sender', 'builder'), 'submit_validation' if target == 'validator' else 'ask_planner')
    if role:
        calls = event.get('tool_calls') or []
        call = calls[0] if calls and isinstance(calls[0], dict) else {}
        name, args = call.get('name'), call.get('args') or {}
        action = (role, {'write_file': 'write_file', 'edit_file': 'edit_file', 'read_file': 'read_file',
                         'open': 'research', 'search': 'research', 'find': 'research',
                         'send_message': 'handoff'}.get(name,
                         'execute_cli' if name == 'exec' and isinstance(args, dict) and args.get('argv')
                         else 'inspect_source' if name == 'exec' else 'thinking'))
    if not action:
        return None
    return {'at': event.get('at'), 'role': action[0], 'action': action[1]}


def _trial(job, root: Path, index: int):
    requests = job.get('requests', [])
    if index < 0 or (requests and index >= len(requests)) or (not requests and index != 0):
        raise ValueError('请求序号不存在')
    request = requests[index] if requests else {}
    owned = root / 'trials' / job['id']
    if not owned.resolve().is_relative_to(root.resolve()):
        raise ValueError('创建记录目录异常')
    folders = []
    if owned.exists():
        for path in owned.glob('*/*/request.json'):
            saved = _json(path, owned).get('request', {})
            if saved.get('name') == request.get('name') and saved.get('category') == request.get('category'):
                folders.append(path.parent)
    folder = max(folders, key=lambda p: p.stat().st_mtime) if folders else owned / '_pending'
    return folder, owned, bool(folders)


def creation_progress(job, root: Path, index: int):
    folder, owned, folders = _trial(job, root, index)
    requests = job.get('requests', [])
    request = requests[index] if requests else {}
    planner = _json(folder / 'site-session.json', owned)
    builder = _json(folder / 'builder.json', owned)
    draft = _json(folder / 'draft.json', owned)
    events = _events(folder / 'events.jsonl', owned)
    validations = sorted(folder.glob('validation-*.json'), key=lambda p: p.stat().st_mtime) if folders else []
    reviews = [_json(path, owned) for path in validations]
    review = reviews[-1] if reviews else {}
    result = next((item for item in job.get('results', []) if item.get('name') == request.get('name')
                   and item.get('category') == request.get('category')), {})
    # 草稿检查点包含增量复用和中断处理后的完整结论，优先于单轮验收快照。
    report = draft.get('validation') or review.get('result') or {}
    states = (report.get('capability_results') or review.get('capability_results')
              or review.get('deterministic', {}).get('capability_results') or {})
    states = {**states, **result.get('capability_results', {})}
    timeline = [item for event in events if (item := _activity(event))]
    last_role = next((item['role'] for item in reversed(timeline) if item['role']), None)
    phase = {'queued': 'queued', 'intent': 'research', 'planned': 'research', 'site_intent': 'research',
             'access_validation': 'validate', 'repair': 'repair', 'done': 'complete'}.get(job.get('stage'), 'build')
    if phase == 'build' and last_role == 'validator':
        phase = 'validate'
    elif phase == 'build' and validations:
        phase = 'repair'
    if job.get('status') == 'queued':
        phase = 'queued'
    if phase == 'complete' and job.get('status') == 'failed':
        phase = {'site_intent': 'research', 'access_validation': 'validate'}.get(
            result.get('failure_stage'), 'validate' if validations else 'build' if draft else 'research')
    if job.get('status') in {'running', 'waiting_user'} and job.get('current_index') not in {None, index}:
        phase = 'complete' if result else 'queued'
    # 恢复会话会复制已有观察，同一真实执行只计一次。
    executions = {}
    for current in reviews:
        for observation in current.get('observations', []):
            args, output = observation.get('args', {}), observation.get('result', {})
            if (observation.get('tool') == 'exec' and (args.get('argv') or args.get('code'))
                    and output.get('execution_id') and output.get('started') is not False):
                executions.setdefault(output['execution_id'], set()).add(args.get('capability_id'))
        for case in current.get('case_results', []):
            execution = case.get('execution', {})
            if (execution_id := execution.get('execution_id')) and execution.get('started') is not False:
                executions.setdefault(execution_id, set()).add(case.get('capability_id'))
    plan = planner.get('plan') or review.get('plan') or {}
    purposes = {cap['id']: cap.get('purpose', cap['id']) for cap in plan.get('capabilities', []) if cap.get('id')}
    capabilities = []
    for cap in dict.fromkeys([*purposes, *(cap for cap in states if cap != 'package' or not purposes)]):
        state = states.get(cap, {})
        editing = (phase in {'build', 'repair'} and job.get('status') not in {'completed', 'partial'}
                   or report.get('stage') == 'edited')
        capabilities.append({'id': cap, 'purpose': purposes.get(cap, cap),
            'status': 'incomplete' if editing else state.get('status', 'incomplete'),
            'deterministic': 'incomplete' if editing else state.get('deterministic', 'incomplete'),
            'semantic': 'incomplete' if editing else state.get('semantic', 'incomplete'),
            'reason': state.get('reason', ''),
            'executions': sum(cap in owners for owners in executions.values()),
            'external_blocked': bool(state.get('external_blocked'))})
    pending = report.get('regression_commands', [])
    return {'job_id': job['id'], 'request_index': index, 'phase': phase,
            'last_activity': timeline[-1]['at'] if timeline else None,
            'validation_rounds': max(len(validations), report.get('validation_rounds', 0)), 'execution_count': len(executions),
            'files': sorted(draft.get('files', {})), 'capabilities': capabilities,
            'regressions': [{'capability_id': item.get('capability_id'), 'reason': item.get('reason', '')}
                            for item in pending],
            'calls': {'planner': planner.get('calls', 0), 'validator': sum(r.get('calls', 0) for r in reviews),
                      'builder': max([builder.get('turns_attempted', 0), *[e.get('turn', 0) for e in events
                                     if e.get('event') == 'model_started']])},
            'events': timeline[-18:]}


def creation_rounds(job, root: Path, index: int):
    """读取角色每轮回复与工具调用；历史记录按调用内容匹配已保存回执。"""
    folder, owned, found = _trial(job, root, index)
    events = _events(folder / 'events.jsonl', owned, tail_bytes=None)
    planner = _json(folder / 'site-session.json', owned)
    reviews = ([_json(path, owned) for path in sorted(folder.glob('validation-*.json'),
                                                    key=lambda path: path.stat().st_mtime)] if found else [])
    observations = {
        'planner': [item for item in planner.get('observations', []) if item.get('actor') == 'planner'],
        'validator': [],
    }
    seen = set()
    for review in reviews:
        for item in review.get('observations', []):
            if item.get('id') not in seen:
                observations['validator'].append(item)
                seen.add(item.get('id'))
    receipts = {event.get('call_id'): event.get('content') for event in events
                if event.get('event') in {'tool_result', 'agent_tool_result'} and event.get('call_id')}
    roles = {'site_intent_response': 'planner', 'model_completed': 'builder',
             'access_validation_response': 'validator'}
    rounds = {role: [] for role in roles.values()}
    for event in events:
        role = roles.get(event.get('event'))
        if not role:
            continue
        calls = []
        for call in event.get('tool_calls') or []:
            if not isinstance(call, dict):
                continue
            name, args = call.get('name', ''), call.get('args') or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    pass
            result = receipts.get(call.get('id'))
            if result is None and role in observations:
                match = next((item for item in observations[role]
                              if item.get('tool') == name and item.get('args') == args), None)
                if match is not None:
                    result = match.get('result')
                    observations[role].remove(match)
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except ValueError:
                    pass
            calls.append({'name': name, 'id': call.get('id'), 'args': args, 'result': result})
        rounds[role].append({'number': len(rounds[role]) + 1, 'at': event.get('at'),
                             'content': event.get('content'), 'reasoning': event.get('reasoning'),
                             'tool_calls': calls})
    return {'job_id': job['id'], 'request_index': index, 'roles': rounds}
