"""QA 管线的离线回归测试，不调用真实模型。"""
import asyncio
import base64
import csv
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from eval.benchmarks.gaia import GaiaSample, load_samples
from eval.qa import final_orchestrator_output, judge_answer
from eval.runner import _run_one, aggregate_xbench


def test_gaia_ids_and_validation(tmp_path):
    data = tmp_path / 'gaia.jsonl'
    data.write_text('\n'.join(json.dumps({'question': f'q{i}', 'answer': i}) for i in range(3)))
    assert [s.id for s in load_samples(data, ids=['gaia_0002'])] == ['gaia_0002']
    assert load_samples(data)[0].answer == '0'
    with pytest.raises(ValueError):
        load_samples(data, ids=['absent'])


def test_xbench_encoded_and_plain(tmp_path):
    from eval.benchmarks.xbench import _xor
    from eval.benchmarks.xbench import load_samples as load_x
    data = tmp_path / 'x.csv'
    with data.open('w') as f:
        w = csv.DictWriter(f, fieldnames=['id', 'canary', 'prompt', 'answer'])
        w.writeheader()
        w.writerow({'id': '1', 'canary': 'test', **{
            k: base64.b64encode(_xor(v.encode(), 'test')).decode()
            for k, v in [('prompt', 'question'), ('answer', 'gold')]}})
    assert load_x(data)[0].answer == 'gold'
    plain = tmp_path / 'x.jsonl'
    plain.write_text(json.dumps({'id': '2', 'question': 'q', 'answer': 'a'}))
    assert load_x(plain)[0].query == 'q'


def conversation(workspace, messages):
    p = workspace / 'conversations/snapshots/orchestrator.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'messages': messages}))
    return p


def test_final_answer_replays_journal_and_ignores_reasoning(tmp_path):
    conversation(tmp_path, [{'role': 'assistant', 'content': 'intermediate'}])
    journal = tmp_path / 'conversations/journals/orchestrator.jsonl'
    journal.parent.mkdir()
    journal.write_text(json.dumps({'message': {'role': 'assistant', 'content': [
        {'type': 'reasoning', 'text': 'secret'}, {'type': 'text', 'text': 'final'}]}}) + '\n')
    assert final_orchestrator_output(tmp_path) == 'final'


def test_tool_turn_is_not_final(tmp_path):
    conversation(tmp_path, [{'role': 'assistant', 'content': 'old'},
                           {'role': 'assistant', 'content': 'searching'},
                           {'role': 'tool_call', 'content': '{}'}])
    with pytest.raises(ValueError):
        final_orchestrator_output(tmp_path)


def test_legacy_conversation_and_empty_final(tmp_path):
    path = tmp_path / 'conversations/orchestrator.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'messages': [{'role': 'assistant', 'content': 'answer'}]}))
    assert final_orchestrator_output(tmp_path) == 'answer'
    conversation(tmp_path, [{'role': 'assistant', 'content': 'old'},
                           {'role': 'assistant', 'content': ''}])
    with pytest.raises(ValueError):
        final_orchestrator_output(tmp_path)


def test_judge_success_failure_timeout():
    sample = GaiaSample('1', 'question', 'gold')
    async def run():
        judge = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps(
            {'correct': True, 'extracted_answer': 'gold', 'reason': 'equivalent'}))))
        result = await judge_answer('final', sample, judge=judge)
        assert result['score'] == 1
        messages = judge.ainvoke.call_args.args[0]
        assert json.loads(messages[1].content)['prediction'] == 'final'
        judge.ainvoke.return_value = SimpleNamespace(content='not json')
        assert (await judge_answer('final', sample, judge=judge))['score'] is None
        judge.ainvoke.return_value = SimpleNamespace(content=json.dumps(
            {'correct': False, 'extracted_answer': None, 'reason': 'no answer'}))
        null_answer = await judge_answer('final', sample, judge=judge)
        assert null_answer['status'] == 'ok' and null_answer['score'] == 0
        assert null_answer['extracted'] == ''
        async def slow(_):
            await asyncio.sleep(1)
        judge.ainvoke = slow
        assert (await judge_answer('final', sample, judge=judge, timeout=.001))['status'] == 'judge_error'
    asyncio.run(run())


@pytest.mark.parametrize('benchmark', ['gaia', 'xbench'])
def test_qa_runner_uses_only_final_and_rejudges_without_search(tmp_path, benchmark):
    workspace = tmp_path / 'workspace'
    conversation(workspace, [{'role': 'assistant', 'content': 'Final answer: 42'}])
    (workspace / 'output').mkdir()
    (workspace / 'output/eval_table.md').write_text('WRONG TABLE')
    result = SimpleNamespace(workspace_path=str(workspace), token_usage={})
    harness = SimpleNamespace(run=AsyncMock(return_value=result))
    factory = lambda _: harness
    grader = AsyncMock(return_value={'status': 'judge_error', 'score': None})
    sample = GaiaSample('1', 'original question', '42')
    async def run():
        kwargs = dict(benchmark=benchmark, grade_fn=grader, run_tag='test', output_dir=tmp_path,
                      sem=asyncio.Semaphore(1), harness_factory=factory)
        with patch('eval.preprocess.clean_query', new_callable=AsyncMock) as cleaner:
            first = await _run_one(sample, **kwargs)
            cleaner.assert_not_called()
        assert first['pred'] == 'Final answer: 42'
        assert harness.run.call_args.args[0] == 'original question'
        grader.return_value = {'status': 'ok', 'score': 1}
        second = await _run_one(sample, **kwargs)
        assert second['metrics']['score'] == 1
        assert harness.run.await_count == 1
        await _run_one(sample, **kwargs)
        assert grader.await_count == 2
        from eval.rescore import _grade_one
        await _grade_one(tmp_path / '1', sample, grader, asyncio.Semaphore(1), asyncio.get_running_loop())
        assert grader.await_count == 3
        assert harness.run.await_count == 1
    asyncio.run(run())


def test_unscored_is_not_wrong():
    result = aggregate_xbench([{'metrics': {'score': 1}}, {'metrics': {'score': 0}},
                               {'metrics': {'score': None, 'error': 'timeout'}}])
    assert result['accuracy'] == .5
    assert result['n_unscored'] == 1 and not result['complete']
