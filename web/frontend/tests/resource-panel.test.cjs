const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const test = require('node:test');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const exports_ = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/components/drawer/ResourcePanel.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText, { exports: exports_, require });

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
