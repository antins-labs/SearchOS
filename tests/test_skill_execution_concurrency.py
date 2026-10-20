"""并发 Skill Execution 回归：真实文件锁与 ToolNode，使用本地执行替身。"""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from searchos.tools.skills import execution as se
from searchos.tools.search_state import _workspace_var, _current_task_id_var, _source_scope_var
from searchos.skills.core.schema import parse_skill_file
from searchos.socm.storage.workspace import WorkspaceManager
from searchos.tools.simple_browser import state, tools

@pytest.fixture
def context(tmp_path, monkeypatch):
    package = tmp_path / 'sample-skill'
    package.mkdir()
    (package / 'SKILL.md').write_text('---\nname: sample-skill\ndescription: Sample CLI\nmetadata:\n  searchos-category: access\n---\nOriginal instructions\n')
    (package / 'run.py').write_text('print(1)')
    skill = parse_skill_file(package)
    monkeypatch.setattr(se, '_skill', lambda name: skill)
    root = tmp_path / 'session'
    ws = WorkspaceManager(tmp_path, session_id='session')
    ws.create()
    monkeypatch.setattr(ws, 'load_state', lambda: SimpleNamespace(intent='original research query'))
    tokens = [(state._browser_var, state._browser_var.set(state.BrowserState())), (_workspace_var, _workspace_var.set(ws)), (_current_task_id_var, _current_task_id_var.set('task-a')),
              (_source_scope_var, _source_scope_var.set({'mode': 'web'}))]
    yield root, package
    for var, token in reversed(tokens):
        var.reset(token)


def execute(call='call-1', argv=None, **kwargs):
    return se.exec_skill.coroutine('sample-skill', argv or ['python', 'run.py'], call, **kwargs)


def install_runner(monkeypatch, payload=None):
    calls = []
    async def runtime(skill_dir, argv, *, work_dir, execution_dir, **kwargs):
        calls.append({'work': work_dir, 'skill': skill_dir, **kwargs})
        execution_id = kwargs['execution_id']
        saved = execution_dir / execution_id
        artifact = saved / 'artifacts' / 'result.json'
        se._write_json(artifact, payload or {'message': 'diagnostic'})
        result = {'execution_id': execution_id, 'status': 'completed', 'started': True,
                  'exit_code': 0, 'stdout': '', 'stderr': '', 'truncated': False,
                  'artifacts': [{'id': 'result.json', 'path': 'result.json', 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
        se._write_json(saved / 'record.json', result)
        return result
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', runtime)
    return calls


from langchain_core.messages import ToolMessage
from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState


@pytest.mark.asyncio
async def test_parallel_exec_calls_in_one_agent_wait_for_shared_work_directory(context, monkeypatch):
    """同轮工具批次可并发投递；宿主排队，模型不应为工作目录锁重试。"""
    se.load_package('sample-skill')
    first_started, release, second_submitted = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen = []
    runtime = install_runner(monkeypatch)
    from searchos.skills.runtime import command_runtime
    original = command_runtime.run_command
    async def delayed(*args, **kwargs):
        seen.append(kwargs['work_dir'])
        if len(seen) == 1:
            first_started.set()
            await release.wait()
            (kwargs['work_dir'] / 'previous-output.txt').write_text('preserved')
        else:
            assert (kwargs['work_dir'] / 'previous-output.txt').read_text() == 'preserved'
        return await original(*args, **kwargs)
    monkeypatch.setattr(command_runtime, 'run_command', delayed)
    first = asyncio.create_task(execute('first'))
    await asyncio.wait_for(first_started.wait(), 1)
    async def second_call():
        second_submitted.set()
        return await execute('second')
    second = asyncio.create_task(second_call())
    try:
        await asyncio.wait_for(second_submitted.wait(), 1)
        assert not second.done(), 'shared-work contention must wait instead of returning blocked'
        assert len(seen) == 1
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert all(json.loads(result[0])['status'] == 'completed' for result in results)
    assert len(runtime) == 2 and seen[0] == seen[1]


@pytest.mark.asyncio
@pytest.mark.parametrize('bind_task', [True, False])
async def test_different_subagents_execute_same_skill_concurrently(context, monkeypatch, bind_task):
    from searchos.tools.search_state import _current_agent_var
    both_started, release = asyncio.Event(), asyncio.Event()
    seen = []
    install_runner(monkeypatch)
    from searchos.skills.runtime import command_runtime
    original = command_runtime.run_command
    async def delayed(*args, **kwargs):
        seen.append(kwargs['work_dir'])
        if len(seen) == 2:
            both_started.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(command_runtime, 'run_command', delayed)
    async def agent(name, task):
        _current_agent_var.set(name)
        _current_task_id_var.set(task if bind_task else '')
        se.load_package('sample-skill')
        return await execute('same-call-id')
    pending = [asyncio.create_task(agent('search_agent_1', 'frontier-1')),
               asyncio.create_task(agent('search_agent_2', 'frontier-2'))]
    try:
        await asyncio.wait_for(both_started.wait(), 1)
        assert len(set(seen)) == 2
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*pending), 2)
    assert all(json.loads(result[0])['status'] == 'completed' for result in results)


@pytest.mark.asyncio
async def test_tool_node_parallel_exec_batch_completes_without_model_retry(context, monkeypatch):
    """复现真实入口：一条模型消息中的两个 exec 由 ToolNode 并发分发。"""
    from langchain_core.messages import AIMessage
    from langgraph.prebuilt import ToolNode
    from langgraph.graph import END, START, MessagesState, StateGraph
    from searchos.skills.runtime import command_runtime

    se.load_package('sample-skill')
    calls = install_runner(monkeypatch)
    original_run, original_acquire = command_runtime.run_command, se._acquire_work_lock
    both_submitted, release = asyncio.Event(), asyncio.Event()
    submitted = 0
    async def acquire(lock):
        nonlocal submitted
        submitted += 1
        if submitted == 2:
            both_submitted.set()
        await original_acquire(lock)
    async def delayed(*args, **kwargs):
        await release.wait()
        return await original_run(*args, **kwargs)
    monkeypatch.setattr(se, '_acquire_work_lock', acquire)
    monkeypatch.setattr(command_runtime, 'run_command', delayed)
    message = AIMessage(content='', tool_calls=[
        {'name': 'exec', 'id': call_id, 'args': {'skill': 'sample-skill', 'argv': ['python', 'run.py']}}
        for call_id in ('batch-1', 'batch-2')
    ])
    graph = StateGraph(MessagesState)
    graph.add_node('tools', ToolNode([se.exec_skill]))
    graph.add_edge(START, 'tools')
    graph.add_edge('tools', END)
    batch = asyncio.create_task(graph.compile().ainvoke({'messages': [message]}))
    try:
        await asyncio.wait_for(both_submitted.wait(), 2)
        assert not batch.done()
    finally:
        release.set()
        output = await asyncio.wait_for(batch, 2)
    results = output['messages'][1:]
    assert {result.tool_call_id for result in results} == {'batch-1', 'batch-2'}
    assert all(json.loads(result.content)['status'] == 'completed' for result in results)
    assert len(calls) == 2 and calls[0]['work'] == calls[1]['work']


@pytest.mark.asyncio
@pytest.mark.parametrize('conflicting_request', [False, True])
async def test_parallel_same_call_id_runs_once_after_wait(context, monkeypatch, conflicting_request):
    se.load_package('sample-skill')
    started, release, submitted = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = install_runner(monkeypatch)
    from searchos.skills.runtime import command_runtime
    original = command_runtime.run_command
    async def delayed(*args, **kwargs):
        started.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(command_runtime, 'run_command', delayed)
    first = asyncio.create_task(execute())
    await asyncio.wait_for(started.wait(), 1)
    async def duplicate():
        submitted.set()
        return await execute(argv=['python', 'run.py', '--different'] if conflicting_request else None)
    second = asyncio.create_task(duplicate())
    try:
        await asyncio.wait_for(submitted.wait(), 1)
        assert not second.done()
    finally:
        release.set()
        first_result, second_result = await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert json.loads(first_result[0])['status'] == 'completed'
    assert second_result[1]['execution']['started'] is False
    if conflicting_request:
        assert 'different request' in json.loads(second_result[0])['error']
    else:
        assert json.loads(second_result[0])['replayed'] is True
    assert len(calls) == 1
    assert json.loads((await execute())[0])['status'] == 'completed'


@pytest.mark.asyncio
async def test_work_lock_wait_timeout_leaves_owner_and_receipts_intact(context, monkeypatch):
    se.load_package('sample-skill')
    started, release = asyncio.Event(), asyncio.Event()
    install_runner(monkeypatch)
    from searchos.skills.runtime import command_runtime
    original = command_runtime.run_command
    async def delayed(*args, **kwargs):
        started.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(command_runtime, 'run_command', delayed)
    monkeypatch.setattr(se, 'WORK_LOCK_WAIT_TIMEOUT_S', 0.02)
    first = asyncio.create_task(execute())
    await asyncio.wait_for(started.wait(), 1)
    try:
        result, artifact = await execute('waiting')
        assert 'timed out waiting' in json.loads(result)['error']
        assert artifact['execution']['started'] is False
        assert not se.execution_started('waiting')
        receipts = list((context[0] / 'skills' / 'calls').glob('*/*.json'))
        assert len(receipts) == 1 and json.loads(receipts[0].read_text())['state'] == 'pending'
        assert not first.done()
    finally:
        release.set()
        await asyncio.wait_for(first, 2)
    assert json.loads((await execute('waiting'))[0])['status'] == 'completed'


@pytest.mark.asyncio
async def test_cancel_releases_lock_and_receipt_prevents_rerun(context, monkeypatch):
    se.load_package('sample-skill')
    calls = []
    started, waiting, cleanup, finish_cleanup = (asyncio.Event() for _ in range(4))
    async def runtime(*args, **kwargs):
        calls.append(1)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await finish_cleanup.wait()
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', runtime)
    async def waiting_call(call):
        waiting.set()
        return await execute(call)
    running = asyncio.create_task(execute())
    await asyncio.wait_for(started.wait(), 1)
    waiter = asyncio.create_task(waiting_call('other'))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        assert not waiter.done()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not se.execution_started('other')
        assert len(list((context[0] / 'skills' / 'calls').glob('*/*.json'))) == 1
        assert not running.done()
        waiting.clear()
        replay_waiter = asyncio.create_task(waiting_call('call-1'))
        await asyncio.wait_for(waiting.wait(), 1)
        running.cancel()
        await asyncio.wait_for(cleanup.wait(), 1)
        assert not replay_waiter.done(), 'owner retains the lock until subprocess cleanup finishes'
        finish_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await running
        replay = json.loads((await asyncio.wait_for(replay_waiter, 2))[0])
        assert replay['status'] == 'cancelled' and replay['replayed']
        install_runner(monkeypatch)
        result = json.loads((await execute('next'))[0])
        assert result['status'] == 'completed'
    finally:
        finish_cleanup.set()
        if not running.done():
            running.cancel()
        await asyncio.gather(running, waiter, return_exceptions=True)
    assert len(calls) == 1


def request(name="exec", call_id="a"):
    return SimpleNamespace(tool_call={"name": name, "args": {}, "id": call_id})


@pytest.mark.asyncio
@pytest.mark.parametrize('waiter_id', ['same', 'different'])
async def test_cancelled_queued_exec_does_not_double_charge_owner(monkeypatch, waiter_id):
    import asyncio
    from searchos.tools.skills import execution as skill_execution

    budget = BudgetState(max_skills=3)
    middleware = BudgetMiddleware(budget, ControlState())
    lock = asyncio.Lock()
    started, queued, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    active_calls = set()
    runs = []
    monkeypatch.setattr(skill_execution, 'execution_started', lambda call_id: call_id in active_calls)
    monkeypatch.setattr('langgraph.config.get_config', lambda: {'configurable': {'thread_id': 'reader'}})
    before_execution = middleware._checkpoint()

    async def handler(req):
        if lock.locked():
            queued.set()
        async with lock:
            call_id = req.tool_call['id']
            active_calls.add(call_id)
            runs.append(call_id)
            started.set()
            await finish.wait()
            return ToolMessage(content='result', tool_call_id=call_id,
                               artifact={'execution': {'started': True}})

    owner = asyncio.create_task(middleware.awrap_tool_call(request(call_id='same'), handler))
    await started.wait()
    waiter = asyncio.create_task(middleware.awrap_tool_call(request(call_id=waiter_id), handler))
    try:
        await queued.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert middleware._reserved['skill'] == 1
        after_cancellation = middleware._checkpoint()
        finish.set()
        result = await owner
        assert runs == ['same']
        assert budget.consumed_skills == 1
        assert not any(middleware._reserved.values())
        # A normal receipt must still preserve the charge across a checkpoint gap.
        assert result.additional_kwargs['sf_budget_receipt']['costs'] == {'skill': 1}
        for saved in (before_execution, after_cancellation):
            restored = BudgetMiddleware(BudgetState(max_skills=3), ControlState())
            await restored.abefore_model({'budget_checkpoint': saved, 'messages': [result]}, None)
            assert restored.budget.consumed_skills == 1
        await middleware.awrap_tool_call(request(call_id='next'), handler)
        assert budget.consumed_skills == 2
    finally:
        finish.set()
        await asyncio.gather(owner, waiter, return_exceptions=True)


@pytest.mark.asyncio
async def test_budget_rejected_duplicate_does_not_hide_owner_charge():
    import asyncio
    from searchos.harness.middleware.utils.messages import is_blocked

    budget = BudgetState(max_skills=1)
    middleware = BudgetMiddleware(budget, ControlState())
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(req):
        calls.append(req.tool_call['id'])
        started.set()
        await finish.wait()
        return ToolMessage(content='result', tool_call_id=req.tool_call['id'],
                           artifact={'execution': {'started': True}})
    owner = asyncio.create_task(middleware.awrap_tool_call(request(call_id='same'), handler))
    try:
        await started.wait()
        duplicate = await middleware.awrap_tool_call(request(call_id='same'), handler)
        assert is_blocked(duplicate) and budget.consumed_skills == 0
        finish.set()
        await owner
        assert calls == ['same'] and budget.consumed_skills == 1
        assert not any(middleware._reserved.values())
    finally:
        finish.set()
        await asyncio.gather(owner, return_exceptions=True)
