"""从长轨迹保留可追溯的调用、失败及任务上下文，避免流式答案挤占预算。"""
from __future__ import annotations

from collections import Counter
import json


def trace_context(text: str, max_chars: int = 63000) -> str:
    if len(text) <= max_chars:
        return text
    candidates = []
    counts = Counter()
    for line_no, line in enumerate(text.splitlines(), 1):
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get('type', '')
        counts[kind] += 1
        if kind not in {'task_start', 'task_complete', 'step'}:
            continue
        action = event.get('action') or {}
        name = action.get('name', '') if isinstance(action, dict) else ''
        observation = str(event.get('observation', ''))
        priority = 4
        if kind in {'task_start', 'task_complete'}:
            priority = 0
        elif name in {'load_skill', 'read_skill_file', 'enqueue_tasks'}:
            priority = 1
        elif name == 'exec':
            priority = 2
            try:
                result = json.loads(observation)
                if isinstance(result, dict) and (result.get('error') or result.get('exit_code') not in (None, 0)
                                                or result.get('status') in {'failed', 'blocked'}):
                    priority = 1
            except ValueError:
                pass
        elif any(word in observation.lower() for word in ('error', 'failed', 'blocked', 'timeout')):
            priority = 3
        compact = {'line': line_no, 'type': kind, 'agent': event.get('agent', '')}
        if kind == 'step':
            compact.update(tool=name, args=json.dumps(action.get('args', {}), ensure_ascii=False)[:1400],
                           observation=observation[:200 if name in {'load_skill', 'read_skill_file'} else 1100],
                           state_delta=event.get('state_delta', {}))
        else:
            compact['record'] = json.dumps(event, ensure_ascii=False)[:2400]
        rendered = json.dumps(compact, ensure_ascii=False)
        candidates.append((priority, line_no, rendered))
    if not candidates:
        return text[:16000] + '\n[中间内容已省略]\n' + text[-(max_chars-16030):]
    header = json.dumps({'trace_summary': '按工具类型优先抽样；不是完整轨迹。line 是原轨迹行号。',
                         'event_counts': dict(counts)}, ensure_ascii=False) + '\n'
    chosen = []
    remaining = max_chars - len(header)
    for _, line_no, rendered in sorted(candidates):
        if len(rendered) + 1 <= remaining:
            chosen.append((line_no, rendered))
            remaining -= len(rendered) + 1
    return header + '\n'.join(record for _, record in sorted(chosen))
