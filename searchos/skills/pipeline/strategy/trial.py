"""在当前 subtask 上应用候选策略，保存产出和独立 Judge 判定。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Callable, Awaitable
from uuid import uuid4

from searchos.skills.packaging import package_fingerprint, snapshot_package, validate_package
from searchos.skills.pipeline.strategy.judge import judge_subtask

SubtaskRunner = Callable[..., Awaitable[dict]]


def save_record(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


async def run_current_subtask(*, subtask: str, strategy: str) -> dict:
    """复用当前 runtime 的模型、工具、预算与来源范围，仅启动检索子 agent。"""
    from searchos.agents.runtime import _ctx
    from searchos.agents.orchestrator.lifecycle import _spawn_sub_agent
    from searchos.tools.search_state import _current_agent_var
    if _ctx.workspace is None or _ctx.model is None:
        raise ValueError('strategy validation requires an active sub-agent runtime or an explicit subtask_runner')
    current = (_ctx.agent_graphs or {}).get(_current_agent_var.get(), {})
    agent_type = current.get('agent_type', 'search_agent')
    if agent_type not in {'search_agent', 'local_search_agent'}:
        agent_type = 'search_agent'
    agent_id = await _spawn_sub_agent(agent_type, subtask, list(current.get('skill_names', ())),
                                     target_table=current.get('target_table', ''), strategy_guidance=strategy)
    task = _ctx.task_pool[agent_id]
    try:
        report = await task
    finally:
        # A timeout/cancellation must not leave the validation agent running.
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    graph = _ctx.workspace.load_state().evidence_graph
    task_ids = set(getattr(report, 'task_ids', ()))
    bound = {b.evidence_id for b in graph.task_bindings if b.task_id in task_ids}
    nodes = [n for n in graph.nodes if n.status.value == 'active' and (not task_ids or n.id in bound)]
    observation_ids = {n.observation_id for n in nodes}
    return {'answer': getattr(report, 'last_message', ''),
            'evidence': [{'claim': n.finding, 'source': n.source, 'excerpt': n.source_excerpt} for n in nodes],
            'sources': [{'source': o.source, 'text': o.text} for o in graph.observations if o.id in observation_ids],
            'error': '' if report.status == 'completed' else f'{report.status}: {report.result}',
            'strategy_applied': _ctx.agent_graphs[agent_id].get('strategy_guidance_applied', False),
            'agent_id': agent_id, 'workspace': str(_ctx.workspace.path),
            'metrics': {'duration_s': getattr(report, 'duration_s', 0)}}


async def validate_strategy(candidate: Path, *, subtask: str, library_path: Path,
                            runner: SubtaskRunner | None = None, judge_model: Any = None,
                            results_root: Path | None = None, timeout_s: float = 120,
                            min_confidence: float = .7) -> tuple[bool, Path, str]:
    root = results_root or library_path.parent / '.skill-trials'
    if root.resolve().is_relative_to(library_path.resolve()):
        relative = root.resolve().relative_to(library_path.resolve())
        if not any(part.startswith(('.', '_')) for part in relative.parts):
            raise ValueError('trial records must be outside the library or in a hidden directory')
    record = root / candidate.name / uuid4().hex
    record.mkdir(parents=True)
    result_path = record / 'result.json'
    result = {'status': 'running', 'created_at': datetime.now(timezone.utc).isoformat(),
              'accepted': False, 'reason': '', 'subtask': subtask, 'min_confidence': min_confidence, 'timeout_s': timeout_s,
              'scope': 'candidate answered current subtask; no causal/generalization claim'}
    save_record(result_path, result)
    try:
        saved_candidate = record / 'candidate' / candidate.name
        snapshot_package(candidate, saved_candidate)
        result['candidate_hash'] = package_fingerprint(saved_candidate)
        result['candidate_path'] = str(saved_candidate)
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('validation timeout must be finite and positive')
        if not subtask.strip():
            raise ValueError('no subtask available for strategy validation')
        guidance = validate_package(saved_candidate).body
        # Separate coroutine context; reuse the live runtime, not a cloned full session.
        outcome = await asyncio.wait_for(asyncio.create_task((runner or run_current_subtask)(
            subtask=subtask, strategy=guidance)), timeout=timeout_s)
        save_record(record / 'outcome.json', outcome)
        if outcome.get('error'):
            raise ValueError(f'subtask execution failed: {outcome["error"]}')
        if not isinstance(outcome.get('answer'), str) or not isinstance(outcome.get('evidence'), list) or not isinstance(outcome.get('sources'), list):
            raise ValueError('subtask runner returned incomplete answer/evidence/sources')
        if outcome.get('strategy_applied') is not True:
            raise ValueError('candidate strategy was not applied by a retrieval agent')
        verdict = await judge_subtask(subtask, outcome, model=judge_model,
                                      record_writer=lambda name, value: save_record(record / name, value))
        save_record(record / 'judge.json', verdict)
        if package_fingerprint(candidate) != result['candidate_hash']:
            raise ValueError('candidate package changed during validation; cannot install an untested version')
        issues = list(verdict['issues'])
        if not outcome['answer'].strip(): issues.append('没有返回子任务答案')
        if not outcome['evidence']: issues.append('没有来源证据')
        if not verdict['answered']: issues.append('Judge 判定未回答子任务')
        if not verdict['grounded']: issues.append('Judge 判定结论缺少来源支持')
        if verdict['confidence'] < min_confidence: issues.append('Judge 判定置信度不足')
        accepted = not issues
        result.update(accepted=accepted, status='passed' if accepted else 'rejected',
                      reason=verdict['reason'] if accepted else '；'.join(issues) + '：' + verdict['reason'],
                      issues=issues, confidence=verdict['confidence'])
    except asyncio.CancelledError:
        result.update(status='cancelled', reason='subtask validation cancelled')
        save_record(result_path, result)
        raise
    except Exception as exc:
        result.update(status='error', reason=f'{type(exc).__name__}: {exc}')
    save_record(result_path, result)
    return result['accepted'], result_path, result['reason']
