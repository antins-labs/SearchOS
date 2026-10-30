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


def _events(path, root):
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            return []
        with path.open('rb') as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - 512_000))
            if size > 512_000:
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


def creation_progress(job, root: Path, index: int):
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
            if observation.get('tool') == 'exec' and args.get('argv') and output.get('execution_id'):
                executions[output['execution_id']] = args.get('capability_id')
        for case in current.get('case_results', []):
            if execution_id := case.get('execution', {}).get('execution_id'):
                executions[execution_id] = case.get('capability_id')
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
            'executions': sum(value == cap for value in executions.values()),
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
