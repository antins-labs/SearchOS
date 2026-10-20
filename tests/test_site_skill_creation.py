"""站点能力集合、双 Agent 交互、完整能力验收与草稿保留。"""
import json
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage

from searchos.skills.intent.site import validate_plan, capability_examples


def plan():
    return {'capabilities': [dict(id=name, purpose=purpose, inputs={'query': '查询词'},
        required_fields=['title', 'source_url'], examples=[{'query': 'alpha'}, {'query': 'beta'}],
        evidence_ids=['obs-1'], depends_on=[])
        for name, purpose in [('search', '搜索记录'), ('detail', '读取实体')]], 'limitations': []}


def boundary_case(**updates):
    return dict({'input': {'query': 'observed-empty'}, 'expected_status': 'empty',
                 'reason': '已读取的原生结果页明确显示无匹配记录。', 'evidence_ids': ['obs-1']}, **updates)


@pytest.mark.parametrize('cases', [
    [boundary_case(input={'query': 'alpha'})],
    [boundary_case(), boundary_case(expected_status='ok')],
])
def test_boundary_inputs_cannot_duplicate_or_contradict_locked_cases(cases):
    value = plan(); value['capabilities'][0]['boundary_cases'] = cases
    with pytest.raises(ValueError, match='distinct'):
        validate_plan(value, [{'id': 'obs-1', 'tool': 'web_open', 'usable': True}])


@pytest.mark.asyncio
@pytest.mark.parametrize('fresh', [False, True])
async def test_intent_can_only_add_boundary_cases_with_fresh_page_evidence(tmp_path, fresh):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    workspace = BuilderWorkspace(tmp_path/'package')
    try:
        session = SiteIntentSession(None, workspace, BuildRecord(tmp_path/'record'))
        session.state.update(plan=plan(), observations=[{'id': 'obs-1', 'tool': 'web_open', 'usable': True}])
        workspace.set_validation_examples(capability_examples(session.state['plan']))
        initial = deepcopy(session.state['plan'])
        async def converse(*args, **kwargs):
            oid = session.observe('web_open', {'id_or_url': 'https://example.com/no-match'},
                {'content': 'No matching records', 'live_evidence': True}, 'intent') if fresh else 'obs-1'
            return {'status': 'clarified', 'guidance': '新增已核实的无匹配边界，保留原能力。',
                    'evidence_ids': [oid], 'boundary_additions': [boundary_case(evidence_ids=[oid])]}
        session.converse = converse
        if not fresh:
            with pytest.raises(ValueError, match='newly opened'):
                await session.advise('search', '无匹配结果也应纳入验收', ['obs-1'])
            assert session.state['plan'] == initial
            assert workspace.examples == capability_examples(initial)
        else:
            result = await session.advise('search', '无匹配结果也应纳入验收', ['obs-1'])
            assert len(workspace.examples) == len(capability_examples(initial)) + 1
            assert result['contract_revision'] == 1 and result['requirements_unchanged']
            assert session.state['initial_plan'] == initial
            assert session.state['plan']['capabilities'][0]['examples'] == initial['capabilities'][0]['examples']
            assert session.state['plan']['capabilities'][0]['required_fields'] == initial['capabilities'][0]['required_fields']
            assert session.state['revisions'][0]['boundary_additions'][0]['expected_status'] == 'empty'
            assert workspace.examples[-1]['check_kind'] == 'boundary'
            assert json.loads(session.path.read_text())['plan'] == session.state['plan']
    finally:
        workspace.close()


def test_optional_boundary_cases_compile_without_changing_old_positive_examples():
    original = plan()
    positives = capability_examples(original)
    value = deepcopy(original)
    value['capabilities'][0]['boundary_cases'] = [boundary_case(),
        boundary_case(input={'query': None}, expected_status='invalid_input', reason='接口要求查询词为非空字符串。')]
    validated = validate_plan(value, [{'id': 'obs-1', 'usable': True, 'tool': 'web_open'}])
    compiled = capability_examples(validated)
    assert compiled[:len(positives)] == positives
    boundaries = compiled[len(positives):]
    assert [case['expected_status'] for case in boundaries] == ['empty', 'invalid_input']
    assert all(case['check_kind'] == 'boundary' and case['capability_id'] == 'search' for case in boundaries)
    assert json.loads(boundaries[0]['argv'][-1]) == {'query': 'observed-empty'}
    assert capability_examples(validate_plan(original, [{'id': 'obs-1', 'usable': True}])) == positives


@pytest.mark.parametrize('cases', [
    [boundary_case()] * 4,
    [boundary_case(input={'undeclared': 'x'})], [boundary_case(input=None)],
    [boundary_case(expected_status='error')], [boundary_case(expected_status=None)],
    [boundary_case(reason='  ')], [boundary_case(evidence_ids=[])],
    [boundary_case(evidence_ids=['unknown'])], [boundary_case(evidence_ids=['obs-search'])],
])
def test_boundary_cases_require_bounded_declared_inputs_and_page_evidence(cases):
    value = plan(); value['capabilities'][0]['boundary_cases'] = cases
    with pytest.raises(ValueError, match='boundary_cases'):
        validate_plan(value, [{'id': 'obs-1', 'tool': 'web_open', 'usable': True},
                              {'id': 'obs-search', 'tool': 'web_search', 'usable': True}])


def test_new_boundary_cannot_claim_legacy_observation_without_a_page_tool():
    value = plan(); value['capabilities'][0]['boundary_cases'] = [boundary_case()]
    with pytest.raises(ValueError, match='boundary_cases'):
        validate_plan(value, [{'id': 'obs-1', 'usable': True}])


def test_builder_receives_boundary_page_evidence_with_the_locked_plan(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.intent.site import SiteIntentSession
    session = SiteIntentSession(None, None, SimpleNamespace(root=tmp_path))
    session.state['plan'] = plan()
    session.state['plan']['capabilities'][0]['boundary_cases'] = [boundary_case(evidence_ids=['obs-2'])]
    session.state['observations'] = [
        {'id': 'obs-1', 'tool': 'web_open', 'result': {'content': 'normal page'}},
        {'id': 'obs-2', 'tool': 'web_open', 'result': {'content': 'boundary page explicitly confirms no matches'}},
    ]
    assert 'boundary page explicitly confirms no matches' in session.builder_notes()


@pytest.mark.parametrize('examples', [[{}], [{}, {}]])
def test_no_argument_feed_does_not_require_invented_inputs(examples):
    value = plan()
    value['capabilities'][0].update(id='get_live_alerts', inputs={}, examples=examples)
    original = deepcopy(value)
    result = validate_plan(value, [{'id': 'obs-1', 'usable': True}])
    assert result['capabilities'][0]['examples'] == [{}]
    assert len(capability_examples(result)) == 3
    assert value == original


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
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from types import SimpleNamespace
    class Intent:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(content='', tool_calls=[dict(id='plan', name='submit_site_plan', args=plan())])
    model = Intent()
    session = SiteIntentSession(model, SimpleNamespace(), BuildRecord(tmp_path / 'record'))
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
async def test_intent_reserves_submission_and_repair_inside_eight_calls(tmp_path):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
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
                return AIMessage(content='', tool_calls=[dict(id=str(self.calls), name='web_search', args={'query':'docs'})])
            assert self.tools == {'submit_site_plan'}
            proposal = plan()
            if self.calls == 6:
                proposal['capabilities'][0]['inputs'] = ['query']
            else:
                assert 'search.inputs' in messages[-1].content
            return AIMessage(content='', tool_calls=[dict(id=str(self.calls), name='submit_site_plan', args=proposal)])
    model = Intent()
    session = SiteIntentSession(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path/'record'))
    result = await session.prepare('example.com', ['https://example.com'], '获取信息')
    assert result == plan() and model.calls == 7
    assert len(requests) == 6  # 一次预读 + 五次研究；提交不执行网页工具。
    assert session.state['validation_errors'][0]['call'] == 6


@pytest.mark.asyncio
async def test_invalid_unlocked_proposal_resumes_with_repair_and_preserves_history(tmp_path):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from types import SimpleNamespace
    invalid = plan()
    invalid['capabilities'][0]['inputs'] = ['query']
    original = {'version':1, 'host':'example.com', 'plan':None, 'last_proposal':invalid,
        'calls':8, 'dialogues':[], 'observations':[{'id':'obs-1','usable':True}]}
    prior = tmp_path/'prior.json'; prior.write_text(json.dumps(original))
    class Intent:
        def bind_tools(self, definitions):
            assert 'submit_site_plan' in {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            assert 'search.inputs' in str(messages)
            return AIMessage(content=json.dumps(plan()))
    session = SiteIntentSession(Intent(), SimpleNamespace(), BuildRecord(tmp_path/'resumed'))
    assert await session.prepare('example.com', [], '', resume=prior) == plan()
    assert session.state['calls'] == 9
    assert json.loads(prior.read_text()) == original
    assert session.state['proposal_history'][0] == invalid


@pytest.mark.asyncio
async def test_unlocked_proposal_is_recalibrated_even_when_its_schema_now_passes(tmp_path):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from types import SimpleNamespace
    original = {'version': 1, 'host': 'example.com', 'plan': None, 'last_proposal': plan(),
                'calls': 8, 'dialogues': [], 'observations': [{'id': 'obs-1', 'usable': True}]}
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps(original))
    revised = plan(); revised['capabilities'] = revised['capabilities'][:1]
    revised['capabilities'][0].update(inputs={}, examples=[{}], evidence_ids=['obs-2'])
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
            assert '原提案尚未锁定' in str(messages) and 'current feed only' in str(messages)
            return AIMessage(content='', tool_calls=[dict(id='plan', name='submit_site_plan', args=revised)])
    model = Intent()
    session = SiteIntentSession(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path / 'resumed'))
    assert await session.prepare('example.com', ['https://example.com/news'], '读取入口新闻', resume=prior) == revised
    assert model.calls == 1 and session.state['calls'] == 9
    assert reads == [('web_open', {'id_or_url': 'https://example.com/news'})]
    assert session.state['proposal_history'][0] == original['last_proposal']
    assert json.loads(prior.read_text()) == original


@pytest.mark.asyncio
async def test_locked_plan_resume_neither_researches_nor_replans(tmp_path):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from types import SimpleNamespace
    original = {'version': 1, 'host': 'example.com', 'plan': plan(), 'last_proposal': {'capabilities': []},
                'calls': 8, 'dialogues': [], 'observations': [{'id': 'obs-1', 'usable': True}]}
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps(original))
    session = SiteIntentSession(None, SimpleNamespace(), BuildRecord(tmp_path / 'resumed'))
    assert await session.prepare('example.com', ['https://example.com/news'], '', resume=prior) == plan()
    assert session.state['calls'] == 8 and session.state['observations'] == original['observations']


@pytest.mark.asyncio
async def test_unlocked_resume_is_bounded_to_two_research_and_three_submission_calls(tmp_path):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from types import SimpleNamespace
    original = {'version': 1, 'host': 'example.com', 'plan': None, 'last_proposal': plan(),
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
            if self.calls <= 2:
                return AIMessage(content='', tool_calls=[dict(id=str(self.calls), name='web_search', args={'query': 'docs'})])
            assert self.tools == {'submit_site_plan'}
            return AIMessage(content='invalid JSON')
    model = Intent()
    session = SiteIntentSession(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path / 'resumed'))
    with pytest.raises(ValueError, match='budget exhausted'):
        await session.prepare('example.com', ['https://example.com/news'], '', resume=prior)
    assert model.calls == 5 and session.state['calls'] == 13
    assert len(reads) == 3  # 一次入口刷新、两次模型研究，其余只能提交。
    assert json.loads(session.path.read_text())['calls'] == 13
    assert json.loads(prior.read_text()) == original


@pytest.mark.asyncio
async def test_planning_failure_persists_its_stage_without_starting_builder(tmp_path, monkeypatch):
    from searchos.skills import SkillRequest, run_pipeline
    from searchos.skills.pipeline.access.browser import ResearchBrowser
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
        model=builder, access_site_intent=True, access_intent_model=intent)
    assert result.status == 'error' and result.failure_stage == 'site_intent'
    assert result.to_report()['failure_stage'] == 'site_intent'
    saved = json.loads(result.trial_path.read_text())
    assert saved['failure_stage'] == 'site_intent'
    assert saved['diagnostics']['turns_attempted'] == 0
    assert intent.calls == 8 and builder.calls == 0


@pytest.mark.parametrize('bad', ['evidence', 'duplicate', 'cycle', 'identical_examples'])
def test_plan_rejects_unfounded_or_inconsistent_contract(bad):
    value = plan()
    if bad == 'evidence': value['capabilities'][0]['evidence_ids'] = ['invented']
    if bad == 'duplicate': value['capabilities'][1]['id'] = 'search'
    if bad == 'cycle': value['capabilities'][0]['depends_on'] = ['search']
    if bad == 'identical_examples': value['capabilities'][0]['examples'][1] = {'query': 'alpha'}
    with pytest.raises(ValueError):
        validate_plan(value, [{'id': 'obs-1', 'usable': True}])


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
    from searchos.skills.pipeline.access.browser import ResearchBrowser

    async def research(self, name, args):
        return {'content': 'Public documentation: search records and read entity details. https://example.com/docs'}
    monkeypatch.setattr(ResearchBrowser, 'dispatch', research)
    site_plan = plan()
    site_plan['capabilities'][0].update(inputs={}, examples=[{}])

    class Intent:
        calls = 0
        def bind_tools(self, definitions):
            assert {'web_search', 'web_open', 'web_find'} <= {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content=json.dumps(site_plan))
            assert 'question' in messages[1].content
            return AIMessage(content=json.dumps({'status': 'clarified', 'guidance': 'detail 按实体标识读取，不能返回搜索列表。', 'evidence_ids': ['obs-1']}))

    class Builder:
        calls = 0
        def bind_tools(self, definitions):
            assert 'ask_intent_agent' in {t['function']['name'] for t in definitions}
            return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                assert '站点能力集合' in messages[1].content
                return AIMessage(content='', tool_calls=[dict(id='question', name='ask_intent_agent', args={
                    'capability_id': 'detail', 'question': '详情操作应读取实体还是列表？', 'evidence_ids': ['obs-1']})])
            if self.calls == 2:
                assert '不能返回搜索列表' in messages[-1].content
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
            return AIMessage(content='完成')
    intent = Intent()
    results = await generate_skills(SkillSignal('site', host='example.com', text='搜索和实体详情'),
        library_path=tmp_path/'library', trial_root=tmp_path/'trials', intent_model=intent, builder_model=Builder())
    assert len(results) == 1 and results[0].status == 'installed', results[0].error
    session = json.loads((results[0].trial_path.parent/'site-session.json').read_text())
    assert len(session['plan']['capabilities']) == 2 and len(session['dialogues']) == 1
    assert intent.calls == 2
    draft = json.loads((results[0].trial_path.parent/'draft.json').read_text())
    assert len(draft['examples']) == 3
    assert {e['capability_id'] for e in draft['examples']} == {'search', 'detail'}
    assert len(list((tmp_path/'library/access').iterdir())) == 1


@pytest.mark.asyncio
async def test_capability_gate_checks_every_operation_and_required_field(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    from searchos.skills.pipeline.access.valid import validate_examples
    seen = []
    async def execute(package, argv, **kwargs):
        if '--help' in argv: return {'exit_code': 0}
        seen.append(argv[2])
        row = {'source_url': 'https://example.com/a', 'id': 'a'}
        if argv[2] == 'search': row['title'] = 'ok'
        return {'exit_code': 0, 'stdout': json.dumps({'status': 'ok', 'records': [row]})}
    monkeypatch.setattr(command_runtime, 'run_command', execute)
    result = await validate_examples(tmp_path, capability_examples(plan()))
    assert not result['valid'] and result['capability_id'] == 'detail'
    assert 'title' in result['error']
    assert seen == ['search', 'search', 'detail']


@pytest.mark.asyncio
async def test_advice_cannot_change_locked_plan_and_budget_survives_resume(tmp_path):
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.pipeline.access.records import BuildRecord
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    class Intent:
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            return AIMessage(content=json.dumps({'status':'blocked','guidance':'需要认证',
                'evidence_ids':['obs-1'], 'capabilities':[]}))
    workspace = BuilderWorkspace(tmp_path/'package')
    try:
        a = SiteIntentSession(Intent(), workspace, BuildRecord(tmp_path/'first'))
        a.state.update(host='example.com', plan=plan(), observations=[{'id':'obs-1','usable':True}])
        frozen = deepcopy(a.state['plan'])
        response = await a.advise('detail', '发现登录阻塞', ['obs-1'])
        assert 'capabilities' not in response and a.state['plan'] == frozen
        b = SiteIntentSession(Intent(), workspace, BuildRecord(tmp_path/'resumed'))
        await b.prepare('example.com', [], '', resume=a.path)
        await b.advise('detail', '再次确认', ['obs-1'])
        assert (await b.advise('detail', '重复', ['obs-1']))['error'] == 'intent_dialogue_budget_exhausted'
        assert b.state['plan'] == frozen and b.state['calls'] == 2
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
])
def test_parse_object_accepts_one_explicit_json_payload(wrapper):
    from searchos.skills.intent.site import parse_object
    expected = plan()
    content = wrapper.format(json.dumps(expected, ensure_ascii=False))
    assert parse_object(AIMessage(content=content)) == expected
    assert parse_object(AIMessage(content=[{'type': 'text', 'text': content}])) == expected


@pytest.mark.parametrize('content', [
    '说明：{"a":1}',
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
])
def test_parse_object_rejects_ambiguous_or_incomplete_payloads(content):
    from searchos.skills.intent.site import parse_object
    with pytest.raises(ValueError):
        parse_object(AIMessage(content=content))
