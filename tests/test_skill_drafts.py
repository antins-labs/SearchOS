"""草稿保留、从候选包续修与发布边界。"""
import asyncio
import json

import pytest
from langchain_core.messages import AIMessage

from searchos.skills.pipeline.access.run import build_skill
from searchos.skills.pipeline.drafts import load_draft, save_draft


DOCUMENT = '---\nname: example-com\ndescription: 查询数据\nmetadata:\n  searchos-category: access\n  host: example.com\n---\npython scripts/search.py\n'


@pytest.mark.asyncio
async def test_exhaustion_saves_complete_draft_and_resume_repairs_it(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    async def command(package, *args, **kwargs):
        fixed = (package / 'scripts/search.py').read_text() == 'print(2)'
        return {'exit_code': 0, 'stdout': json.dumps({'records': [{'url': 'https://example.com/item', 'title': 'data'}]}) if fixed else 'human readable text'}
    monkeypatch.setattr(command_runtime, 'run_command', command)
    class Initial:
        turn = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.turn += 1
            calls = [dict(id='doc', name='write_file', args=dict(path='SKILL.md', content=DOCUMENT)),
                     dict(id='script', name='write_file', args=dict(path='scripts/search.py', content='print(1)')),
                     dict(id='sample', name='register_example', args=dict(argv=['python3', 'scripts/search.py'], output='', records_key='records'))]
            return AIMessage(content='', tool_calls=calls if self.turn == 1 else [])
    target = tmp_path / 'example-com'
    first = tmp_path / 'first'
    assert await build_skill('example.com', [], builder_model=Initial(), output_dir=target,
                             record_dir=first, max_turns=2) is None
    package, saved = load_draft(first / 'draft.json')
    assert not target.exists() and not list(tmp_path.glob('.staging*'))
    assert (package / 'scripts/search.py').read_text() == 'print(1)'
    assert saved['examples'][0]['records_key'] == 'records'
    assert saved['validation']['stage'] == 'examples'
    class Repair:
        turn = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.turn += 1
            assert 'scripts/search.py' in messages[1].content
            assert '上一轮验证结果' in messages[1].content
            assert '"index": 0' in messages[1].content and 'replace_index' in messages[1].content
            return AIMessage(content='', tool_calls=[dict(id='fix', name='edit_file', args=dict(
                path='scripts/search.py', old_text='print(1)', new_text='print(2)'))] if self.turn == 1 else [])
    second = tmp_path / 'second'
    assert await build_skill('example.com', [], builder_model=Repair(), output_dir=target,
        record_dir=second, max_turns=2, resume_draft=first / 'draft.json') == target
    assert (target / 'SKILL.md').read_text() == DOCUMENT
    assert (target / 'scripts/search.py').read_text() == 'print(2)'
    assert load_draft(second / 'draft.json')[1]['validation']['valid']
    assert (package / 'scripts/search.py').read_text() == 'print(1)'
    assert 'resumed' in (second / 'events.jsonl').read_text()


@pytest.mark.asyncio
async def test_cancellation_preserves_even_invalid_metadata(tmp_path):
    ready = asyncio.Event()
    class Model:
        turn = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.turn += 1
            if self.turn == 1:
                return AIMessage(content='', tool_calls=[dict(id='write', name='write_file', args=dict(
                    path='SKILL.md', content='unfinished metadata'))])
            ready.set()
            await asyncio.Event().wait()
    task = asyncio.create_task(build_skill('example.com', [], builder_model=Model(),
        output_dir=tmp_path / 'example-com', record_dir=tmp_path / 'record'))
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    package, _ = load_draft(tmp_path / 'record/draft.json')
    assert (package / 'SKILL.md').read_text() == 'unfinished metadata'
    assert json.loads((tmp_path / 'record/builder.json').read_text())['exit_reason'] == 'cancelled'


def test_draft_integrity_and_path_boundary(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'SKILL.md').write_text('unfinished')
    pointer = save_draft(tmp_path / 'record', source, ['SKILL.md'], name='example-com', examples=[], require_host=True)
    package, data = load_draft(pointer)
    (package / 'SKILL.md').write_text('tampered')
    with pytest.raises(ValueError, match='hash mismatch'): load_draft(pointer)
    data['package'] = '../source'; pointer.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='package path'): load_draft(pointer)
    with pytest.raises(ValueError, match='inside'):
        save_draft(tmp_path / 'other', source, ['../secret'], name='example-com', examples=[], require_host=True)


@pytest.mark.asyncio
async def test_resume_rejects_changed_update_base(tmp_path):
    from dataclasses import asdict
    from searchos.skills import SkillRequest, run_pipeline
    library = tmp_path / 'library'
    package = library / 'access/example-com'; package.mkdir(parents=True)
    (package / 'SKILL.md').write_text(DOCUMENT)
    request = SkillRequest('access', 'example-com', 'query', host='example.com', action='update', reason='需要分页')
    pointer = save_draft(tmp_path / 'record', package, ['SKILL.md'], name='example-com', examples=[], require_host=True)
    (pointer.parent / 'request.json').write_text(json.dumps(dict(request=asdict(request), base_hash='outdated')))
    result = await run_pipeline(request, library_path=library, resume_draft=pointer)
    assert result.status == 'error' and 'changed since' in result.error
    assert (package / 'SKILL.md').read_text() == DOCUMENT
