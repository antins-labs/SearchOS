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
const start = (id, tool = 'inspect_table') => event({ type:'tool_call_started',agent:'orchestrator',tool,tool_call_id:id,args:{table_id:id},reasoning:'开始 '+id });
const step = (id, tool = 'inspect_table') => event({ type:'step',agent:'orchestrator',tool_call_id:id,action:{name:tool,args:{table_id:id}},observation:'结果 '+id });
const html = (events) => renderToStaticMarkup(React.createElement(timeline,{events}));

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
  const error = event({type:'tool_call_failed',agent:'orchestrator',tool:'inspect_table',tool_call_id:'a',status:'cancelled',error:'已取消'});
  const result = html([start('a'),start('b'),error]);
  assert.match(result,/inspect_table · 已取消/);
  assert.equal((result.match(/animate-spin/g)||[]).length,1);
  const { foldWorkers } = load('lib/derive.ts');
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
