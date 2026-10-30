"""站点研究计划、角色交接、完整能力验收与草稿保留。"""
import json
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage

from searchos.skills.pipeline.access import CONTRACT_VERSION
from searchos.skills.pipeline.access.agents.planner import validate_plan

pytestmark = pytest.mark.usefixtures('deterministic_validation_agent')


def plan():
    return {'capabilities': [dict(id=name, purpose=purpose, evidence_ids=['obs-1'], depends_on=[])
        for name, purpose in [('search', '搜索记录'), ('detail', '读取实体')]], 'limitations': []}


def examples():
    return [{'capability_id': name, 'required_fields': ['title', 'source_url'],
             'argv': ['python', 'scripts/access.py', name, '--input', json.dumps({'query': query})],
             'output': '', 'records_key': 'records', 'source_key': 'source_url'}
            for name in ('search', 'detail') for query in ('alpha', 'beta')]


@pytest.mark.parametrize('capability_count', [6, 20])
def test_site_plan_accepts_all_discovered_capabilities(capability_count):
    value = plan()
    template = value['capabilities'][0]
    value['capabilities'] = [
        {**deepcopy(template), 'id': f'cap_{index}',
         'depends_on': [f'cap_{index - 1}'] if index else []}
        for index in range(capability_count)
    ]
    assert validate_plan(value, [{'id': 'obs-1', 'tool': 'web_open', 'usable': True}]) == value


def test_plan_ignores_interface_declarations_and_preserves_research():
    value = plan()
    value['capabilities'][0].update(inputs={'q': '查询'}, required_fields=['forced'],
        examples=[{'q': 'alpha'}], boundary_cases=[{'input': {'q': ''}}],
        acceptance=['覆盖文章与回答'], implementation='已观察接口返回 article 和 answer 类型')
    original = deepcopy(value)
    result = validate_plan(value, [{'id': 'obs-1', 'tool': 'web_open', 'usable': True}])
    cap = result['capabilities'][0]
    assert not {'inputs', 'required_fields', 'examples', 'boundary_cases'} & cap.keys()
    assert cap['acceptance'] == ['覆盖文章与回答'] and cap['implementation']
    assert value == original


@pytest.mark.parametrize('change', [
    {'purpose': ''}, {'acceptance': '字段名'}, {'depends_on': ['missing']},
    {'depends_on': ['search']}, {'evidence_ids': ['missing']},
])
def test_plan_still_checks_goals_dependencies_and_evidence(change):
    value = plan()
    value['capabilities'][0].update(change)
    with pytest.raises(ValueError):
        validate_plan(value, [{'id': 'obs-1', 'tool': 'web_open', 'usable': True}])


def test_builder_receives_referenced_research_without_fixed_interface(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    session = SitePlannerAgent(None, None, SimpleNamespace(root=tmp_path))
    session.state['plan'] = plan()
    session.state['observations'] = [
        {'id': 'obs-1', 'tool': 'web_open', 'result': {'content': 'Observed authors and full text'}},
    ]
    notes = session.builder_notes()
    assert 'Observed authors and full text' in notes
    assert 'python scripts/access.py' not in notes and '"status":"ok"' not in notes


@pytest.mark.parametrize('result', [
    {'content': '[FETCH_ERROR] reason=network_failure status=0'},
    {'content': 'L2: [NOTE] Live fetch failed; the content below is the search-engine snippet, not the full page.'},
    {'content': 'cached snippet', 'content_source': 'search_fallback'},
])
def test_fetch_error_cannot_support_a_capability_in_legacy_records(result):
    with pytest.raises(ValueError, match='evidence'):
        validate_plan(plan(), [{'id': 'obs-1', 'usable': True,
            'tool': 'web_open', 'result': result}])


@pytest.mark.parametrize('observation', [
    {'id': 'obs-1', 'tool': 'web_search', 'usable': True, 'result': {'content': 'search snippet'}},
    {'id': 'obs-1', 'tool': 'web_open', 'usable': True, 'result': {'content': 'cached snippet', 'live_evidence': False}},
    {'id': 'obs-1', 'tool': 'web_open', 'usable': True, 'result': {'content': 'cached snippet', 'content_source': 'search_cache'}},
])
def test_search_results_without_a_read_page_cannot_lock_a_capability(observation):
    with pytest.raises(ValueError, match='successfully read page'):
        validate_plan(plan(), [observation])


@pytest.mark.asyncio
async def test_structured_submission_storage_error_stops_after_one_model_call(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from types import SimpleNamespace
    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(content=json.dumps(plan()))
    model = Intent()
    session = SitePlannerAgent(model, SimpleNamespace(), BuildRecord(tmp_path / 'record'))
    session.state['observations'] = [{'id': 'obs-1', 'usable': True}]
    save = session.save
    def fail_proposal_save():
        if session.state.get('last_proposal') is not None:
            raise OSError('disk full while persisting proposal')
        save()
    monkeypatch.setattr(session, 'save', fail_proposal_save)
    with pytest.raises(OSError, match='disk full'):
        await session.converse([], 8, validator=lambda value: validate_plan(value, session.state['observations']))
    assert model.calls == 1 and session.state['calls'] == 1
    assert not session.state.get('validation_errors')
    assert json.loads(session.path.read_text())['calls'] == 1


@pytest.mark.asyncio
async def test_intent_can_research_and_correct_submission_within_regular_calls(tmp_path):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from types import SimpleNamespace
    requests = []
    class Browser:
        async def dispatch(self, name, args):
            requests.append((name, args))
            return {'content': 'public page', 'live_evidence': True}
    class Intent:
        calls = 0
        def bind_tools(self, definitions):
            self.tools = {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls <= 5:
                return AIMessage(content='', tool_calls=[dict(id=str(self.calls), name='search', args={'query':'docs'})])
            assert {'search', 'open', 'find', 'exec'} == self.tools
            proposal = plan()
            if self.calls == 6:
                proposal['capabilities'][0]['acceptance'] = 'invalid'
            else:
                assert 'search.acceptance' in messages[-1].content
            return AIMessage(content=json.dumps(proposal))
    model = Intent()
    session = SitePlannerAgent(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path/'record'))
    result = await session.prepare('example.com', ['https://example.com'], '获取信息')
    assert result == plan() and model.calls == 7
    assert len(requests) == 6  # 一次预读 + 五次研究；提交不执行网页工具。
    assert session.state['validation_errors'][0]['call'] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize('final_response', ['plan', 'malformed', 'tool'])
async def test_advice_reserves_final_json_repair_calls_within_total_budget(tmp_path, final_response):
    from types import SimpleNamespace
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    reads = []
    class Browser:
        async def dispatch(self, name, args):
            reads.append((name, args))
            return {'content': 'Public source', 'live_evidence': True}
    class Model:
        calls = 0
        bindings = 0
        def bind_tools(self, definitions):
            self.bindings += 1
            assert {'search', 'find', 'open', 'exec'} == {tool['function']['name'] for tool in definitions}
            owner = self
            class Bound:
                async def ainvoke(self, messages):
                    return await owner.respond(messages)
            return Bound()
        async def ainvoke(self, messages):
            raise AssertionError('所有阶段均使用已绑定的四工具目录。')
        async def respond(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content='', tool_calls=[dict(id='research', name='open',
                    args={'id_or_url': 'https://example.com/docs'})])
            assert self.calls in (2, 3) and '最终整理阶段' in messages[-1].content
            assert '最终 JSON' in messages[-1].content
            if final_response == 'tool':
                return AIMessage(content='', tool_calls=[dict(id='late', name='open',
                    args={'id_or_url': 'https://example.com/late'})])
            return AIMessage(content=json.dumps(plan()) if final_response == 'plan' else '{}')
    model = Model()
    session = SitePlannerAgent(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path / 'record'))
    invoke = lambda: session.converse([], 2, response_validator=lambda value: validate_plan(value, session.state['observations']))
    if final_response == 'plan':
        assert await invoke() == plan()
    else:
        with pytest.raises(ValueError, match='budget exhausted'):
            await invoke()
    expected_calls = 2 if final_response == 'plan' else 3
    assert model.calls == session.state['calls'] == expected_calls and model.bindings == 1
    assert len(reads) == 1  # 收尾与修正轮拦截研究调用，保留正常研究结果。
    if final_response == 'tool':
        assert all('finalization_tool_blocked' in item['result']['error']
                   for item in session.state['observations'][1:])


@pytest.mark.asyncio
async def test_invalid_unlocked_proposal_resumes_with_repair_and_preserves_history(tmp_path):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from types import SimpleNamespace
    invalid = plan()
    invalid['capabilities'][0]['acceptance'] = 'invalid'
    original = {'version':CONTRACT_VERSION, 'host':'example.com', 'plan':None, 'last_proposal':invalid,
        'calls':8, 'dialogues':[], 'observations':[{'id':'obs-1','tool':'web_open','usable':True}]}
    prior = tmp_path/'prior.json'; prior.write_text(json.dumps(original))
    class Intent:
        def bind_tools(self, definitions):
            assert 'open' in {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            assert 'previous_proposal' in str(messages)
            return AIMessage(content=json.dumps(plan()))
    session = SitePlannerAgent(Intent(), SimpleNamespace(), BuildRecord(tmp_path/'resumed'))
    assert await session.prepare('example.com', [], '', resume=prior) == plan()
    assert session.state['calls'] == 9
    assert json.loads(prior.read_text()) == original
    assert session.state['proposal_history'][0] == invalid


@pytest.mark.asyncio
async def test_unlocked_proposal_is_recalibrated_even_when_its_schema_now_passes(tmp_path):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from types import SimpleNamespace
    original = {'version': CONTRACT_VERSION, 'host': 'example.com', 'plan': None, 'last_proposal': plan(),
                'calls': 8, 'dialogues': [], 'observations': [{'id': 'obs-1', 'usable': True}]}
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps(original))
    revised = plan(); revised['capabilities'] = revised['capabilities'][:1]
    revised['capabilities'][0].update(evidence_ids=['obs-2'])
    reads = []
    class Browser:
        async def dispatch(self, name, args):
            reads.append((name, args))
            return {'content': 'The news page exposes a current feed only.', 'live_evidence': True}
    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            assert 'previous_proposal' in str(messages) and 'current feed only' in str(messages)
            return AIMessage(content=json.dumps(revised))
    model = Intent()
    session = SitePlannerAgent(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path / 'resumed'))
    assert await session.prepare('example.com', ['https://example.com/news'], '读取入口新闻', resume=prior) == revised
    assert model.calls == 1 and session.state['calls'] == 9
    assert reads == [('web_open', {'id_or_url': 'https://example.com/news'})]
    assert session.state['proposal_history'][0] == original['last_proposal']
    assert json.loads(prior.read_text()) == original


@pytest.mark.asyncio
async def test_locked_plan_resume_neither_researches_nor_replans(tmp_path):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from types import SimpleNamespace
    original = {'version': CONTRACT_VERSION, 'host': 'example.com', 'plan': plan(), 'last_proposal': {'capabilities': []},
                'calls': 8, 'dialogues': [], 'observations': [
                    {'id': 'obs-1', 'tool': 'web_open', 'usable': True}]}
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps(original))
    session = SitePlannerAgent(None, SimpleNamespace(), BuildRecord(tmp_path / 'resumed'))
    assert await session.prepare('example.com', ['https://example.com/news'], '', resume=prior) == plan()
    assert session.state['calls'] == 8 and session.state['observations'] == original['observations']


@pytest.mark.asyncio
async def test_unlocked_resume_uses_configured_planning_budget(tmp_path):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from types import SimpleNamespace
    original = {'version': CONTRACT_VERSION, 'host': 'example.com', 'plan': None, 'last_proposal': plan(),
                'calls': 8, 'dialogues': [], 'observations': [{'id': 'obs-1', 'usable': True}]}
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps(original))
    reads = []
    class Browser:
        async def dispatch(self, name, args):
            reads.append((name, args))
            return {'content': 'public page', 'live_evidence': True}
    class Intent:
        calls = 0
        def bind_tools(self, definitions):
            self.tools = {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls <= 5:
                return AIMessage(content='', tool_calls=[dict(id=str(self.calls), name='search', args={'query': 'docs'})])
            assert {'search', 'open', 'find', 'exec'} == self.tools
            return AIMessage(content='invalid JSON')
    model = Intent()
    session = SitePlannerAgent(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path / 'resumed'), max_turns=5)
    with pytest.raises(ValueError, match='budget exhausted'):
        await session.prepare('example.com', ['https://example.com/news'], '', resume=prior)
    assert model.calls == 6 and session.state['calls'] == 14
    assert len(reads) == 4  # 一次入口刷新与三次研究，末三轮用于整理和纠错。
    assert json.loads(session.path.read_text())['calls'] == 14
    assert json.loads(prior.read_text()) == original


@pytest.mark.asyncio
async def test_planning_failure_persists_its_stage_without_starting_builder(tmp_path, monkeypatch):
    from searchos.skills import SkillRequest, run_pipeline
    from searchos.skills.pipeline.access.tools.web import ResearchBrowser
    async def research(self, name, args):
        return {'content': 'public documentation', 'live_evidence': True}
    monkeypatch.setattr(ResearchBrowser, 'dispatch', research)
    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(content='malformed JSON')
    class Builder:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            raise AssertionError('计划失败时不能启动 Builder')
    intent, builder = Intent(), Builder()
    result = await run_pipeline(SkillRequest('access', 'example-com', '获取站点信息', host='example.com',
        probe_urls=('https://example.com/',)), library_path=tmp_path / 'library', trial_root=tmp_path / 'trials',
        model=builder, access_site_intent=True, access_intent_model=intent, access_planner_max_turns=8)
    assert result.status == 'error' and result.failure_stage == 'site_intent'
    assert result.to_report()['failure_stage'] == 'site_intent'
    saved = json.loads(result.trial_path.read_text())
    assert saved['failure_stage'] == 'site_intent'
    assert saved['diagnostics']['turns_attempted'] == 0
    assert intent.calls == 9 and builder.calls == 0


@pytest.mark.parametrize('bad', ['evidence', 'duplicate', 'cycle'])
def test_plan_rejects_unfounded_or_inconsistent_contract(bad):
    value = plan()
    if bad == 'evidence': value['capabilities'][0]['evidence_ids'] = ['invented']
    if bad == 'duplicate': value['capabilities'][1]['id'] = 'search'
    if bad == 'cycle': value['capabilities'][0]['depends_on'] = ['search']
    with pytest.raises(ValueError):
        validate_plan(value, [{'id': 'obs-1', 'tool': 'web_open', 'usable': True}])


@pytest.fixture
def capability_source():
    """本地来源让整链样例真实区分联网成功和断网失败。"""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({'title': 'local record'}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/record'
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.asyncio
async def test_site_entry_uses_intent_dialogue_and_builds_one_multicapability_package(tmp_path, monkeypatch, capability_source):
    from searchos.skills import generate_skills, SkillSignal
    from searchos.skills.pipeline.access.tools.web import ResearchBrowser

    async def research(self, name, args):
        return {'content': 'Public documentation: search records and read entity details. '
                           'The local source returns title=local record. https://example.com/docs',
                'live_evidence': True, 'content_source': 'page'}
    monkeypatch.setattr(ResearchBrowser, 'dispatch', research)
    site_plan = plan()

    class Intent:
        calls = 0
        def bind_tools(self, definitions):
            assert {'search', 'open', 'find', 'exec'} == {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content=json.dumps(site_plan))
            if self.calls == 2:
                assert 'question' in messages[1].content
                return AIMessage(content=json.dumps({'status': 'clarified', 'guidance': 'detail 按实体标识读取，不能返回搜索列表。', 'evidence_ids': ['obs-1']}))

    class Builder:
        calls = 0
        def bind_tools(self, definitions):
            assert 'send_message' in {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                assert '站点开发计划' in messages[1].content
                return AIMessage(content='', tool_calls=[dict(id='question', name='send_message', args={'role': 'planner', 'content': {
                    'capability_id': 'detail', 'question': '详情操作应读取实体还是列表？', 'evidence_ids': ['obs-1']}})])
            if self.calls == 2:
                advice = next(message for message in reversed(messages)
                              if getattr(message, 'tool_call_id', None) == 'question')
                assert '不能返回搜索列表' in advice.content
                assert '2/50' in messages[-1].content
                script = 'SOURCE = ' + repr(capability_source) + '\n' + '''import argparse,json,sys,urllib.request
p=argparse.ArgumentParser();p.add_argument('operation');p.add_argument('--input');a=p.parse_args()
inputs=json.loads(a.input)
if not isinstance(inputs,dict):
    print(json.dumps({'status':'invalid_input','records':[],'warnings':['input must be an object']}));sys.exit(1)
try:
    with urllib.request.urlopen(SOURCE,timeout=3) as response:
        record=json.load(response)
    record['source_url']=SOURCE
    print(json.dumps({'status':'ok','records':[record],'warnings':[]}))
except OSError as error:
    print(json.dumps({'status':'network_error','records':[],'warnings':[str(error)]}));sys.exit(1)
'''
                return AIMessage(content='', tool_calls=[
                    dict(id='doc', name='write_file', args={'path':'SKILL.md', 'content':'---\nname: example-com\ndescription: 搜索与详情\nmetadata:\n  searchos-category: access\n  host: example.com\n---\npython scripts/access.py search --input JSON\npython scripts/access.py detail --input JSON\n'}),
                    dict(id='code', name='write_file', args={'path':'scripts/access.py','content':script})])
            if self.calls == 3:
                return AIMessage(content='', tool_calls=[dict(id='validate', name='send_message',
                    args={'role': 'validator', 'content': {'examples': examples()}})])
            return AIMessage(content='完成')
    intent = Intent()
    results = await generate_skills(SkillSignal('site', host='example.com', text='搜索和实体详情'),
        library_path=tmp_path/'library', trial_root=tmp_path/'trials', intent_model=intent, builder_model=Builder())
    assert len(results) == 1 and results[0].status == 'installed', results[0].error
    session = json.loads((results[0].trial_path.parent/'site-session.json').read_text())
    assert len(session['plan']['capabilities']) == 2 and len(session['dialogues']) == 1
    assert intent.calls == 2
    draft = json.loads((results[0].trial_path.parent/'draft.json').read_text())
    assert draft['examples'] == []
    assert draft['validation']['valid']
    assert set(draft['validation']['capability_results']) == {'search', 'detail'}
    assert len(list((tmp_path/'library/access').iterdir())) == 1


@pytest.mark.asyncio
async def test_capability_gate_checks_every_operation_and_required_field(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    from searchos.skills.pipeline.access.validation.checks import validate_examples
    seen = []
    async def execute(package, argv, **kwargs):
        if '--help' in argv: return {'exit_code': 0}
        seen.append(argv[2])
        row = {'source_url': 'https://example.com/a', 'id': 'a'}
        if argv[2] == 'search': row['title'] = 'ok'
        return {'exit_code': 0, 'stdout': json.dumps({'status': 'ok', 'records': [row]})}
    monkeypatch.setattr(command_runtime, 'run_command', execute)
    result = await validate_examples(tmp_path, examples())
    assert not result['valid'] and result['capability_id'] == 'detail'
    assert 'title' in result['error']
    assert seen == ['search', 'search', 'detail', 'detail']
    assert len(result['case_results']) == 4
    assert result['capability_results']['search']['deterministic'] == 'passed'
    assert result['capability_results']['detail']['status'] == 'unavailable'


@pytest.mark.asyncio
async def test_message_history_and_plan_survive_resume(tmp_path):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from searchos.skills.pipeline.access.pipeline import AccessPipeline
    class Intent:
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            return AIMessage(content=json.dumps({'status':'blocked','guidance':'需要认证',
                'evidence_ids':['obs-1']}))
    workspace = AccessPipeline(tmp_path/'package')
    try:
        first = SitePlannerAgent(Intent(), workspace, BuildRecord(tmp_path/'first'))
        first.state.update(host='example.com', plan=plan(), observations=[
            {'id':'obs-1','tool':'web_open','usable':True}])
        await first.receive_message('发现登录阻碍')
        resumed = SitePlannerAgent(Intent(), workspace, BuildRecord(tmp_path/'resumed'))
        await resumed.prepare('example.com', [], '', resume=first.path)
        await resumed.receive_message({'question': '再次确认访问条件'})
        assert (await resumed.receive_message('请说明下一步'))['status'] == 'blocked'
        assert resumed.state['plan'] == plan()
        assert resumed.state['calls'] == len(resumed.state['dialogues']) == 3
    finally:
        workspace.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('corrected', [True, False])
async def test_message_plan_revision_is_validated_before_commit(tmp_path, corrected):
    from searchos.skills.pipeline.access.agents.planner import SitePlannerAgent
    from searchos.skills.pipeline.access.artifacts import BuildRecord
    from searchos.skills.pipeline.access.pipeline import AccessPipeline
    original = plan()
    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            assert session.state['plan'] == original
            revised = deepcopy(original)
            revised['capabilities'][0]['acceptance'] = ['保留文章与回答']
            if self.calls == 1 or not corrected:
                revised['capabilities'][0]['acceptance'] = 'invalid'
            return AIMessage(content=json.dumps({'status': 'clarified', 'guidance': '修正已核实的标识。',
                'evidence_ids': ['obs-1'], 'plan': revised}))
    workspace = AccessPipeline(tmp_path/'package')
    try:
        model = Intent()
        session = SitePlannerAgent(model, workspace, BuildRecord(tmp_path/'record'), max_turns=2)
        session.state.update(plan=deepcopy(original), observations=[
            {'id': 'obs-1', 'tool': 'web_open', 'usable': True}])
        workspace.validation.set_validation_examples(examples())
        if corrected:
            result = await session.receive_message('请核实开发输入')
            assert result['plan'] == session.state['plan']
            assert session.state['initial_plan'] == original
            assert len(session.state['revisions']) == 1 and model.calls == 2
        else:
            with pytest.raises(ValueError, match='site planner message.*search.acceptance'):
                await session.receive_message('请核实开发输入')
            assert session.state['plan'] == original and not session.state.get('revisions')
            assert model.calls == 3
        assert workspace.validation.examples == examples()
        assert len(session.state['dialogues']) == 1
        assert all(item['kind'] == 'advice_validation' for item in session.state['validation_errors'])
    finally:
        workspace.close()


def test_draft_checkpoints_are_bounded_and_identical_files_are_reused(tmp_path):
    from searchos.skills.pipeline.drafts import save_draft, load_draft
    source = tmp_path/'source'; source.mkdir()
    record = tmp_path/'record'
    for i in range(12):
        (source/'SKILL.md').write_text(str(i))
        pointer = save_draft(record, source, ['SKILL.md'], name='example-com', examples=[], require_host=True)
        assert len(list((record/'drafts').iterdir())) <= 2
    first = load_draft(pointer)[0]
    save_draft(record, source, ['SKILL.md'], name='example-com', examples=[], require_host=True, validation={'valid':True})
    assert load_draft(pointer)[0] == first
    assert (first/'SKILL.md').read_text() == '11'


@pytest.mark.parametrize('wrapper', [
    '{}',
    '```json\n{}\n```',
    '```\n{}\n```',
    '根据已观察的页面内容，直接输出站点能力计划：\n\n```json\n{}\n```',
    '站点能力计划：\n```JSON\n{}\n```\n以上为已观察范围。',
    '根据已观察的页面内容，站点能力计划如下：\n{}\n以上为已观察范围。',
    'URL 使用 {{city_id}}，另一个未配平的 {{ 是说明文字。\n{}',
])
def test_parse_object_accepts_one_explicit_json_payload(wrapper):
    from searchos.skills.pipeline.access.agents.planner import parse_object
    expected = plan()
    content = wrapper.format(json.dumps(expected, ensure_ascii=False))
    assert parse_object(AIMessage(content=content)) == expected
    assert parse_object(AIMessage(content=[{'type': 'text', 'text': content}])) == expected


@pytest.mark.parametrize('content', [
    '{"a":1}\n{"b":2}',
    '```json\n{"a":1}\n{"b":2}\n```',
    '```json\n{"a":1}\n```\n```json\n{"b":2}\n```',
    '```json\n{"a":1}\n```\n```\n{"b":2}\n```',
    '{"a":1}\n```json\n{"b":2}\n```',
    '```json\n{"a":1}\n```\n{"b":2}',
    '说明\n```json\n{"a":1',
    '说明\n```json\n{"a":1\n```',
    '说明\n```json\n[{"a":1}]\n```',
    '```python\n{"a":1}\n```',
    '说明：{"outer":{"a":1}',
    '{"a":1}\n{"outer":{"b":2}',
])
def test_parse_object_rejects_ambiguous_or_incomplete_payloads(content):
    from searchos.skills.pipeline.access.agents.planner import parse_object
    with pytest.raises(ValueError):
        parse_object(AIMessage(content=content))


def resumed_pipeline_fixture(tmp_path, monkeypatch, *, draft=False):
    from dataclasses import asdict
    from searchos.skills import SkillRequest
    from searchos.skills.pipeline.access.tools.web import ResearchBrowser
    from searchos.skills.pipeline.drafts import save_draft
    saved = tmp_path/'saved'; saved.mkdir()
    original = validate_plan(plan(), [{'id': 'obs-1', 'tool': 'web_open', 'usable': True}])
    state = {'version': CONTRACT_VERSION, 'host': 'example.com', 'plan': original,
             'observations': [{'id': 'obs-1', 'tool': 'web_open', 'usable': True,
                               'result': {'content': 'Original public source', 'live_evidence': True}}],
             'calls': 9, 'dialogues': [{'capability_id': 'search', 'question': 'previous', 'answer': {'status': 'clarified'}}]}
    session = saved/'site-session.json'; session.write_text(json.dumps(state))
    request = SkillRequest('access', 'example-com', '读取站点记录', host='example.com', probe_urls=('https://example.com/',))
    episodes = []
    async def episode(self):
        workspace = self.workspace
        episodes.append({'examples': deepcopy(workspace.validation.examples), 'locked': workspace.validation.examples_locked,
                         'files': sorted(workspace.package.files),
                         'plan': deepcopy(workspace.site_intent.state['plan'])})
        return None
    async def browser(self, name, args):
        assert name == 'web_open'
        return {'content': 'Public documentation.', 'live_evidence': True, 'content_source': 'page'}
    monkeypatch.setattr('searchos.skills.pipeline.access.agents.builder.AccessBuilderAgent.run', episode)
    monkeypatch.setattr(ResearchBrowser, 'dispatch', browser)
    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            raise AssertionError('locked plan restoration must not call the model')
    intent = Intent()
    kwargs = {'library_path': tmp_path/'library', 'trial_root': tmp_path/'trials', 'model': intent,
              'access_site_intent': True, 'access_intent_model': intent, 'access_site_session': session}
    if draft:
        source = tmp_path/'draft-source'; source.mkdir()
        (source/'SKILL.md').write_text('unfinished original draft')
        pointer = save_draft(saved, source, ['SKILL.md'], name='example-com',
                             examples=[], require_host=True, contract_version=CONTRACT_VERSION)
        (saved/'request.json').write_text(json.dumps({'request': asdict(request), 'base_hash': None,
                                                     'access_site_intent': True}))
        kwargs['resume_draft'] = pointer
    return request, kwargs, intent, episodes, state


@pytest.mark.asyncio
async def test_locked_plan_pipeline_resume_adds_no_intent_calls(tmp_path, monkeypatch):
    from searchos.skills import run_pipeline
    request, kwargs, model, episodes, original = resumed_pipeline_fixture(tmp_path, monkeypatch)
    result = await run_pipeline(request, **kwargs)
    assert len(episodes) == 1 and model.calls == 0
    assert episodes[0]['examples'] == []
    saved = json.loads((result.trial_path.parent/'site-session.json').read_text())
    assert saved['calls'] == 9 and saved['dialogues'] == original['dialogues']


@pytest.mark.asyncio
async def test_current_draft_resume_preserves_code_without_builder_declarations(tmp_path, monkeypatch):
    import hashlib

    from searchos.skills import run_pipeline
    request, kwargs, model, episodes, original = resumed_pipeline_fixture(
        tmp_path, monkeypatch, draft=True)
    pointer = kwargs['resume_draft']
    draft = json.loads(pointer.read_text())
    source = pointer.parent / draft['package'] / 'scripts/access.py'
    source.parent.mkdir()
    source.write_text('def search(params):\n    return []\n'
                      'def detail(params):\n    return []\n'
                      'HANDLERS = {"search": search, "detail": detail}\n')
    draft['files']['scripts/access.py'] = hashlib.sha256(source.read_bytes()).hexdigest()
    pointer.write_text(json.dumps(draft))
    await run_pipeline(request, **kwargs)
    assert len(episodes) == 1 and model.calls == 0
    assert episodes[0]['examples'] == [] and not episodes[0]['locked']
    assert episodes[0]['files'] == ['SKILL.md', 'scripts/access.py']


@pytest.mark.asyncio
@pytest.mark.parametrize('plan_locked', [False, True])
async def test_resume_before_examples_checkpoint_waits_for_builder_without_rewriting_history(tmp_path, monkeypatch, plan_locked):
    from searchos.skills import run_pipeline
    request, kwargs, _, episodes, original = resumed_pipeline_fixture(tmp_path, monkeypatch, draft=True)
    pointer = kwargs['resume_draft']
    draft = json.loads(pointer.read_text())
    draft['examples'] = []
    pointer.write_text(json.dumps(draft))
    original_plan = deepcopy(original['plan'])
    if not plan_locked:
        original['plan'] = None
        kwargs['access_site_session'].write_text(json.dumps(original))
    previous_draft = pointer.read_bytes()
    previous_session = kwargs['access_site_session'].read_bytes()

    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(content=json.dumps(original_plan))

    intent = Intent()
    kwargs['access_intent_model'] = intent
    result = await run_pipeline(request, **kwargs)
    assert len(episodes) == 1 and not episodes[0]['locked'], result.error
    assert episodes[0]['examples'] == []
    assert intent.calls == (0 if plan_locked else 1)
    saved = json.loads((result.trial_path.parent/'site-session.json').read_text())
    assert saved['plan'] == original_plan
    assert saved['calls'] == original['calls'] + intent.calls
    assert pointer.read_bytes() == previous_draft
    assert kwargs['access_site_session'].read_bytes() == previous_session
