/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const cache = new Map();
function load(name) {
  const filename = path.resolve(__dirname, '../src', name);
  if (cache.has(filename)) return cache.get(filename);
  const exports = {};
  cache.set(filename, exports);
  const source = fs.readFileSync(filename, 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  }}).outputText, { exports, require(dep) {
    if (dep === '@/lib/api') return { getAgentReply: async () => ({ content: '完整回复' }) };
    if (dep.endsWith('ToolCallDetailDialog')) return { __esModule: true, default: () => null };
    if (dep.startsWith('.') || dep.startsWith('@/')) {
      const base = dep.startsWith('@/') ? dep.slice(2) : path.relative(path.join(__dirname,'../src'), path.resolve(path.dirname(filename),dep));
      const file = ['.ts','.tsx'].map(ext => base+ext).find(f => fs.existsSync(path.join(__dirname,'../src',f)));
      return load(file);
    }
    return require(dep);
  }});
  return exports;
}
const timeline = load('components/workbench/OrchestratorTimeline.tsx').default;
const event = (data) => ({ type: 'trajectory', data });
const start = (id, tool = 'read_table') => event({ type:'tool_call_started',agent:'orchestrator',tool,tool_call_id:id,args:{table_id:id},reasoning:'开始 '+id });
const step = (id, tool = 'read_table') => event({ type:'step',agent:'orchestrator',tool_call_id:id,action:{name:tool,args:{table_id:id}},observation:'结果 '+id });
const html = (events) => renderToStaticMarkup(React.createElement(timeline,{events}));

test('初始化和生成阶段随实际工具与结束事件更新', () => {
  const { deriveRunPhase, foldWorkers, runPhaseLabel } = load('lib/runState.ts');
  const phase = (name, status = 'running', agent = 'orchestrator') => event({
    type: 'harness', kind: 'run_phase', phase: name, status, agent,
  });
  const events = [phase('initializing'), phase('initializing', 'done'), phase('generating')];
  assert.equal(deriveRunPhase(events), 'generating');
  assert.equal(runPhaseLabel(deriveRunPhase(events)), '正在生成下一步行动或回答…');
  assert.equal(deriveRunPhase([...events, start('create_schema')]), null);
  assert.equal(deriveRunPhase([...events, event({type:'task_complete'})]), null);
  assert.equal(deriveRunPhase([...events, phase('generating', 'running', 'search_agent')]), 'generating');
  const workerEvents = [phase('generating', 'running', 'search_agent'), phase('generating', 'done', 'search_agent')];
  assert.equal(foldWorkers(workerEvents)[0].status, 'running');
  assert.equal(deriveRunPhase(workerEvents, 'search_agent'), null);
});

test('运行卡片在首轮工具之前显示初始化并隐藏已结束的阶段', () => {
  const Card = load('components/conversation/OrchestrationCard.tsx').default;
  const phase = event({type:'harness', kind:'run_phase', phase:'initializing', status:'running', agent:'orchestrator'});
  const render = (status, sourceMode) => renderToStaticMarkup(React.createElement(Card, {
    events:[phase], workers:[], searchState:null, status, sourceMode, onOpen() {},
  }));
  assert.match(render('running', 'web'), /正在初始化/);
  assert.match(render('running', 'local'), /正在初始化/);
  assert.doesNotMatch(render('completed', 'web'), /正在初始化/);
});

test('运行卡片在有积压时显示抽取中数量', () => {
  const Card = load('components/conversation/OrchestrationCard.tsx').default;
  const searchState = {
    coverage_map: { cells: {} },
    evidence_graph: {
      nodes: [
        { id: 'a', status: 'active' },
        { id: 'c', status: 'candidate' },
      ],
    },
  };
  const html = (pending) => renderToStaticMarkup(React.createElement(Card, {
    events: [], workers: [{ name: 'orchestrator', status: 'running' }],
    searchState, extractionPendingTotal: pending, status: 'running', sourceMode: 'web', onOpen() {},
  }));
  assert.match(html(3), /已采纳/);
  assert.match(html(3), /候选/);
  assert.match(html(3), /3<\/b> 抽取中/);
  assert.doesNotMatch(html(0), /抽取中/);
});

test('等待回执与随后送达的报告分别显示', () => {
  const result = html([
    event({type:'step', agent:'orchestrator', tool_call_id:'wait', action:{name:'check_agents',args:{}},
      observation:'{"await_reports":true}'}),
    event({type:'agent_report', agent:'orchestrator', report:{agent_id:'search_agent', result:'已核验'}}),
  ]);
  assert.match(result, /等待下一份 Agent 报告/);
  assert.ok(result.indexOf('已核验') > result.indexOf('等待下一份 Agent 报告'));
});

test('显式等待显示工具返回的报告、剩余 worker 和超时', () => {
  const checked = (receipt) => event({type:'step', agent:'orchestrator', tool_call_id:'wait',
    action:{name:'check_agents',args:{timeout:5}}, observation:JSON.stringify(receipt)});
  const result = html([checked({reports:[{agent_id:'search_agent', agent_report:{text:'院校名单已核验'}}],
    remaining:1, running_ids:['search_agent_2']})]);
  assert.match(result, /收到 1 份 Agent 报告/);
  assert.equal((result.match(/院校名单已核验/g)||[]).length, 1);
  assert.match(result, /Agent 2/);
  assert.match(result, /View full parameters and output for check_agents/);
  assert.match(html([checked({reports:[], remaining:1, running_ids:['search_agent_2'], timed_out:true})]), /等待报告超时/);
});

test('主时间线按交付顺序显示每份报告和正文，失败报告保留原因', (t) => {
  const report = (data) => event({type:'agent_report', agent:'orchestrator', report:data});
  const events = [
    report({agent_id:'search_agent_2', status:'completed', result:'Completed: +2 evidence',
      agent_report:{text:'GPU 单价已核实。'.repeat(32)+'[价格原文](evidence:e2)'},
      grounded_findings:[{id:'e2', source_urls:['https://example.org/gpu-price']}]}),
    report({agent_id:'search_agent_2', status:'error', result:'来源读取失败'}),
    report({agent_id:'writer_agent', status:'completed', last_message:'比较表已写入'}),
  ];
  const result = html(events);
  assert.match(result, /Agent 2/);
  assert.ok(result.indexOf('GPU 单价已核实') >= 0 && result.indexOf('GPU 单价已核实') < result.indexOf('来源读取失败'));
  assert.match(result, /比较表已写入/);
  assert.equal((result.match(/<details\b/g)||[]).length, 3);
  assert.doesNotMatch(result, /View full parameters|animate-spin/);
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(timeline, {events, agentName:'search_agent_2'})), /GPU 单价/);
  assert.doesNotMatch(result, /价格原文/);
  const useState = React.useState;
  t.mock.method(React, 'useState', (initial) => useState(initial === false ? true : initial));
  const expanded = html(events);
  assert.match(expanded, /href="https:\/\/example.org\/gpu-price"/);
  assert.match(expanded, /查看原始报告/);
  assert.match(expanded, /grounded_findings/);
});

test('子代理最终回复可展开并渲染 Markdown', () => {
  const agent = 'search_agent';
  const events = [event({type:'agent_final', agent, reasoning:'## 结果\n\n- **已确认**'})];
  const result = renderToStaticMarkup(React.createElement(timeline, {events, agentName:agent}));
  assert.match(result, /<details[^>]*><summary[^>]*>最终回复<\/summary>/);
  assert.match(result, /<h3[^>]*>结果<\/h3>/);
  assert.match(result, /<strong[^>]*>已确认<\/strong>/);
});

test('同名并发工具在开始时显示，乱序返回只更新自己的卡片', () => {
  const before = html([start('a'),start('b')]);
  assert.equal((before.match(/animate-spin/g)||[]).length,2);
  assert.match(before,/开始 a/);
  const partial = html([start('a'),start('b'),step('b')]);
  assert.equal((partial.match(/animate-spin/g)||[]).length,1);
  assert.ok(partial.indexOf('开始 a') < partial.indexOf('结果 b'));
  const finished = html([start('a'),start('b'),step('b'),step('a')]);
  assert.equal((finished.match(/animate-spin/g)||[]).length,0);
  assert.ok(finished.indexOf('结果 a') < finished.indexOf('结果 b'));
  assert.equal((finished.match(/View full parameters/g)||[]).length,2);
});

test('中途模型回复不能把整个研究标为完成', () => {
  const draft = event({type:'agent_final',agent:'orchestrator',reasoning:'还需要核实'});
  assert.doesNotMatch(html([draft,start('a')]),/Finished.*synthesized/);
  assert.match(html([draft,step('a'),event({type:'task_complete'})]),/Finished/);
});

test('追问处拆开调用块，后续工具出现在追问下方', () => {
  const Activity = load('components/conversation/TurnActivity.tsx').default;
  const follow = event({type:'harness',kind:'steer_injected',message_id:'s1',text:'补充实验室',mode:'after_tool'});
  const turn = {id:'t',status:'running',events:[step('before'),follow,start('after')],followUps:['补充实验室'],workers:[],searchState:null};
  const result = renderToStaticMarkup(React.createElement(Activity,{turn,onOpen(){}},'最终回答'));
  assert.ok(result.indexOf('结果 before') < result.indexOf('补充实验室'));
  assert.ok(result.indexOf('补充实验室') < result.indexOf('开始 after'));
  assert.equal((result.match(/补充实验室/g)||[]).length,1);
  assert.equal((result.match(/View agents &amp; evidence/g)||[]).length,2);
});

test('失败和取消结束对应调用，不使正在工作的子代理变成已结束', () => {
  const error = event({type:'tool_call_failed',agent:'orchestrator',tool:'read_table',tool_call_id:'a',status:'cancelled',error:'已取消'});
  const result = html([start('a'),start('b'),error]);
  assert.match(result,/read_table · 已取消/);
  assert.equal((result.match(/animate-spin/g)||[]).length,1);
  const { foldWorkers } = load('lib/runState.ts');
  const workers = foldWorkers([event({type:'dispatch',agent:'search_agent'}),event({type:'step',agent:'search_agent',status:'error'})]);
  assert.equal(workers[0].status,'running');
});

test('派发事件更新正在执行的 enqueue 卡片，工具回执不增加重复块', () => {
  const events = [start('queue','enqueue_tasks'),event({type:'dispatch',agent:'search_agent',task:'查询论文'})];
  const running = html(events);
  assert.equal((running.match(/View full parameters/g)||[]).length,1);
  assert.match(running,/查询论文/);
  const done = html([...events,step('queue','enqueue_tasks')]);
  assert.equal((done.match(/View full parameters/g)||[]).length,1);
  assert.match(done,/Dispatched 1 agent/);
  assert.doesNotMatch(done,/animate-spin/);
});

test('相同文字的多次追问各自分段；回执先到和历史回放都不重复', () => {
  const { turnActivitySegments } = load('lib/conversation.ts');
  const first = event({type:'harness',kind:'steer_injected',message_id:'s1',text:'查论文'});
  const second = event({type:'harness',kind:'steer_injected',message_id:'s2',text:'查论文'});
  const interim = turnActivitySegments([step('a'),first,step('b')],['查论文','查论文']);
  assert.equal(interim.length,3);
  assert.equal(interim[2].events.length,0);
  const replay = turnActivitySegments([step('a'),first,step('b'),second,step('c')],['查论文','查论文']);
  assert.equal(replay.length,3);
  assert.equal(replay[1].events[0].data.tool_call_id,'b');
  assert.equal(replay[2].events[0].data.tool_call_id,'c');
  assert.equal(replay[2].key,interim[2].key);
});

test('只有结果的旧轨迹仍显示工具，开始事件重放不会重复创建卡片', () => {
  assert.match(html([step('old')]),/结果 old/);
  const begin = start('a');
  assert.equal((html([begin,begin,step('a')]).match(/View full parameters/g)||[]).length,1);
});

const skill = (id, parent, status = 'running') => event({
  type: 'skill_execution', agent: 'orchestrator', execution_id: id,
  parent_tool_call_id: parent, parent_execution_id: 'exec-' + parent,
  skill: 'weixin-sogou-com', argv: ['python', 'scripts/access.py', 'search_articles'], status,
  observation: status === 'running' ? '' : JSON.stringify({status, stdout: '文章结果 ' + id,
    streams: {stdout: {shown_chars: 12, total_chars: 12, truncated: false}}}),
});

test('一个 Exec 内多个技能子步骤收在默认折叠的详情里，只计一次工具调用', () => {
  const {buildCards} = load('components/workbench/OrchestratorTimeline.tsx');
  const {deriveStepCount, foldWorkers} = load('lib/runState.ts');
  const events = [start('a','exec'), start('b','exec'), skill('child-a','a'), skill('child-b','b'),
    skill('child-b','b','completed'), skill('child-a','a','error'), skill('child-c','a','completed'),
    step('a','exec'), step('b','exec')];
  const cards = buildCards(events, 'completed', []);
  assert.equal(cards.length, 2);
  assert.equal(cards[0].children[0].action.toolCall.executionId, 'child-a');
  assert.equal(cards[0].children[0].action.toolCall.status, 'error');
  assert.equal(cards[1].children[0].action.toolCall.status, 'completed');
  const markup = html(events);
  assert.equal((markup.match(/<details\b/g) || []).length, 2);
  assert.doesNotMatch(markup, /<details[^>]*\bopen\b/);
  assert.match(markup, /<summary[^>]*>技能编排 · 2 个子步骤 · 成功 1 \/ 失败 1<\/summary>.*?文章结果 child-c/);
  assert.match(markup, /<summary[^>]*>技能编排 · 1 个子步骤 · 成功 1<\/summary>.*?文章结果 child-b/);
  assert.equal(deriveStepCount([...events, ...events]), 2);
  assert.equal(buildCards([...events, ...events], 'completed', []).length, 2);
  const workers = foldWorkers([event({type:'dispatch',agent:'search_agent'}),
    {...skill('c','a','error'), data:{...skill('c','a','error').data,agent:'search_agent'}}]);
  assert.equal(workers[0].status,'running');
});

test('父 Exec 尚未返回时子执行已经可见，取消和终止会停止转圈', () => {
  const {buildCards} = load('components/workbench/OrchestratorTimeline.tsx');
  const events = [start('a','exec'), skill('c','a')];
  assert.equal(buildCards(events,'running',[])[0].children[0].action.spin,true);
  assert.equal(buildCards(events,'error',[])[0].children[0].action.spin,false);
  assert.equal(buildCards([...events, skill('c','a','cancelled')],'running',[])[0].children[0].action.toolCall.status,'cancelled');
});

test('回放量子位 case 时通过 parent_execution_id 归组，原日志保持原样', () => {
  const file = path.resolve(__dirname,'../../../searchos_workspace/20261102_212907_44e1b577763a/trajectory.jsonl');
  // 本地验收使用原 case；独立 checkout 由下方固定样例覆盖同一结构。
  const records = fs.existsSync(file) ? fs.readFileSync(file,'utf8').trim().split('\n').map(JSON.parse) : [
    {type:'tool_call_started',agent:'search_agent',tool:'exec',tool_call_id:'p',args:{argv:['searchanything']}},
    {type:'step',agent:'search_agent',tool_call_id:'c',action:{name:'exec',args:{skill:'weixin-sogou-com',argv:['python'],parent_execution_id:'exec-p'}},observation:"{'status':'completed'}"},
    {type:'step',agent:'search_agent',tool_call_id:'p',action:{name:'exec',args:{argv:['searchanything']}},observation:JSON.stringify({execution_id:'exec-p',stdout:'articles'})},
  ];
  const {buildCards} = load('components/workbench/OrchestratorTimeline.tsx');
  const {deriveStepCount} = load('lib/runState.ts');
  const events = records.map(event);
  const cards = buildCards(events,'completed',[],'search_agent');
  assert.equal(cards.filter(c => c.action?.toolCall).length,fs.existsSync(file) ? 8 : 1);
  assert.equal(cards.flatMap(c => c.children || []).length,fs.existsSync(file) ? 8 : 1);
  assert.equal(deriveStepCount(events),fs.existsSync(file) ? 8 : 1);
});

test('execPreview 解析 code/argv 与结构化 stdout', () => {
  const { parseExecArgs, summarizeExecResult, clipLines, isCodeTool } = load('lib/execPreview.ts');
  const coded = parseExecArgs(JSON.stringify({ code: 'print(1)\nprint(2)\nprint(3)' }));
  assert.equal(coded.codeLines, 3);
  assert.match(coded.detail, /python/);
  const argv = parseExecArgs(JSON.stringify({ argv: ['python', 'scripts/run.py'] }));
  assert.match(argv.commandLine, /python/);
  const summary = summarizeExecResult(JSON.stringify({
    exit_code: 0,
    stdout: 'hello\nworld',
    streams: { stdout: { total_chars: 11, truncated: true }, stderr: { total_chars: 0 } },
  }));
  assert.equal(summary.exitCode, 0);
  assert.equal(summary.truncated, true);
  assert.match(summary.metaLine, /exit 0/);
  assert.match(summary.metaLine, /truncated/);
  assert.equal(clipLines('a\nb\nc\nd', 2), 'a\nb\n…');
  assert.equal(isCodeTool({ tool: 'exec' }), true);
  assert.equal(isCodeTool({ kind: 'skill', tool: 'demo' }), true);
  assert.equal(isCodeTool({ tool: 'search' }), false);
});

test('codeHighlight 区分关键字/字符串/注释', () => {
  const { tokenizePython } = load('lib/codeHighlight.tsx');
  const kinds = Object.fromEntries(
    tokenizePython('from x import y  # note\nprint("ok")\n').map((t) => [t.text, t.kind]),
  );
  assert.equal(kinds.from, 'kw');
  assert.equal(kinds.import, 'kw');
  assert.equal(kinds.print, 'fn');
  assert.equal(kinds['"ok"'], 'str');
  assert.equal(kinds['# note'], 'cmt');
});

test('Exec 卡片展示代码摘要与 exit meta，而不是整包 JSON 预览', () => {
  const code = 'from searchos_sdk import skill\nprint("ok")\n';
  const observation = JSON.stringify({
    execution_id: 'exec-1',
    exit_code: 0,
    stdout: 'ok\n',
    streams: { stdout: { total_chars: 3 }, stderr: { total_chars: 0 } },
  });
  const result = html([
    event({
      type: 'tool_call_started', agent: 'orchestrator', tool: 'exec', tool_call_id: 'e1',
      args: { code }, reasoning: '跑一段代码',
    }),
    event({
      type: 'step', agent: 'orchestrator', tool_call_id: 'e1',
      action: { name: 'exec', args: { code } }, observation,
    }),
  ]);
  assert.match(result, /Exec/);
  assert.match(result, /python · \d+ 行/);
  assert.match(result, /trace-tok-kw/);
  assert.match(result, /searchos_sdk/);
  assert.match(result, /exit 0/);
  assert.doesNotMatch(result, /execution_id/);
});

test('无工具追问轮显示基于已有证据作答，而不是空的 Finished', () => {
  const {buildCards} = load('components/workbench/OrchestratorTimeline.tsx');
  const empty = buildCards([event({type: 'task_complete'})], 'completed', []);
  assert.equal(empty.length, 1);
  assert.equal(empty[0].action.label, '基于已有证据作答');
  assert.equal(empty[0].action.detail, '本轮无新的工具调用');
  const withTools = buildCards([
    start('a', 'read_table'),
    step('a', 'read_table'),
    event({type: 'task_complete'}),
  ], 'completed', []);
  assert.equal(withTools.at(-1).action.label, 'Finished & synthesized');
  assert.equal(withTools.at(-1).action.detail, undefined);
});
