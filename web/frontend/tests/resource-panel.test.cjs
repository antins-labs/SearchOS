const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const test = require('node:test');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const exports_ = {};
const derive = {};
const refs = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/socmRefs.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports: refs });
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/runState.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports: derive, require: name => name === '@/lib/socmRefs' ? refs : require(name) });
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/components/drawer/ResourcePanel.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText, { exports: exports_, require: name => name === '@/lib/runState' ? derive : require(name) });

test('资源面板只统计 Agent 的工具调用，排除新旧子步骤及重放事件', () => {
  const event = data => ({ type: 'trajectory', data: { agent: 'search_agent', ...data } });
  const events = [
    event({ type: 'tool_call_started', tool: 'exec', tool_call_id: 'parent' }),
    event({ type: 'step', action: { name: 'exec', args: {} }, tool_call_id: 'parent' }),
    event({ type: 'step', tool_call_id: 'old-child', action: { name: 'exec', args: { skill: 'sample', parent_execution_id: 'exec-parent' } } }),
    event({ type: 'skill_execution', execution_id: 'child', status: 'completed', skill: 'sample', parent_tool_call_id: 'parent' }),
  ];
  const html = renderToStaticMarkup(React.createElement(exports_.default, { turn: {
    meta: {}, events, status: 'completed', workers: [{ name: 'search_agent', status: 'completed', events: [...events, ...events] }],
  } }));
  assert.match(html, /1 次工具调用</);
  assert.doesNotMatch(html, /次技能执行/);
});

test('Usage uses global cache denominator and counts native local tools', () => {
  const html = renderToStaticMarkup(React.createElement(exports_.default, { turn: {
    meta: { tokenUsage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120,
      cached_prompt_tokens: 40, cache_hit_rate: .8, llm_calls: 3 } },
    events: [], status: 'completed', workers: [{ name: 'local_search_agent',
      status: 'completed', events: ['local_catalog', 'local_open', 'local_find'].map(name => ({
        type: 'step', action: { name },
      })) }],
  } }));
  assert.match(html, /40%/);
  assert.doesNotMatch(html, /80%/);
  assert.match(html, /1 search\/catalog · 1 open · 1 find/);
});

test('Missing cache usage stays unknown globally and per role', () => {
  const html = renderToStaticMarkup(React.createElement(exports_.default, { turn: {
    meta: { tokenUsage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120,
      cached_prompt_tokens: 0, llm_calls: 2, cache_unreported_calls: 1, cache_hit_rate: null,
      by_role: { orchestrator: { prompt_tokens: 100, completion_tokens: 20,
        cached_prompt_tokens: 0, llm_calls: 2, cache_unreported_calls: 1 } } } },
    events: [], status: 'completed', workers: [],
  } }));
  assert.match(html, /Input cache hit.*Unknown/);
  assert.match(html, /Cache unknown/);
  assert.match(html, /Known cached/);
  assert.doesNotMatch(html, /0% cached|0 percent cache hit/);
});
