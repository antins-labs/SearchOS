/* eslint-disable @typescript-eslint/no-require-imports -- Node 运行组件交互测试。 */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const plain = (value) => JSON.parse(JSON.stringify(value));

function harness() {
  const context = { settings: { network: { proxy_url: '', auto_route: true, routes: {}, source: 'settings', credential_set: false } },
    uiPrefs: { language: 'zh' }, async mutate(args) { const view = await args.call(); this.settings = args.merge(this.settings, view); return view; } };
  context.mutate = context.mutate.bind(context);
  const states = [], calls = [];
  let cursor = 0, disabled = false;
  const exports = {};
  const source = readFileSync(join(__dirname, '../src/components/settings/diagnostics/NetworkSettings.tsx'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText, { exports, require(name) {
    if (name === 'react') return { ...React, useState(initial) { const i = cursor++;
      if (!(i in states)) states[i] = initial;
      return [states[i], (value) => { states[i] = typeof value === 'function' ? value(states[i]) : value; }]; } };
    if (name === '@/components/settings/SettingsProvider') return { useSettings: () => context };
    if (name === '@/components/settings/controls/Toggle') return { __esModule: true, default: 'toggle' };
    if (name === '@/components/settings/controls/TextField') return { __esModule: true, default: 'field' };
    if (name === '@/components/settings/primitives') return { Card: 'section', Row: 'row' };
    if (name === '@/lib/api') return {
      async putNetwork(patch) { calls.push({ save: plain(patch) }); return { ...context.settings.network, ...patch }; },
      async getNetworkRoutes() { return { routes: [{ host: 'example.com', port: 443, route: 'direct', expires_at: 2000000000 }] }; },
      async clearNetworkRoutes(host) { calls.push({ clear: host || 'all' }); return { routes: [] }; },
      async testNetwork(url) { calls.push({ check: url }); return { ok: true, attempts: [{ route: 'direct', ok: true, phase: 'connected' }] }; },
    };
    return require(name);
  } });
  return { context, calls, setDisabled(value) { disabled = value; }, render() { cursor = 0; return exports.default({ disabled }); } };
}

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  for (const child of React.Children.toArray(node.props?.children)) { const found = find(child, predicate); if (found) return found; }
  return null;
}
const label = (tree, text) => find(tree, (node) => (node.props?.['aria-label'] ?? node.props?.label) === text);
const button = (tree, text) => find(tree, (node) => node.type === 'button' && React.Children.toArray(node.props.children).some((child) => child === text));
const settle = () => new Promise((resolve) => setImmediate(resolve));

test('普通设置无需域名，代理和自动选线使用同一个设置接口', async () => {
  const h = harness();
  assert.equal(label(h.render(), '覆盖规则主机'), null);
  const field = find(label(h.render(), '代理地址'), (node) => node.type === 'field');
  await field.props.onCommit('http://127.0.0.1:7890');
  const toggle = find(label(h.render(), '自动选择可用线路'), (node) => node.type === 'toggle');
  await toggle.props.onChange(false);
  assert.deepEqual(h.calls, [{ save: { proxy_url: 'http://127.0.0.1:7890' } }, { save: { auto_route: false } }]);
});

test('高级区可查看清除自动记录，并添加和删除人工规则', async () => {
  const h = harness();
  button(h.render(), '高级网络诊断').props.onClick();
  await settle();
  await label(h.render(), '清除 example.com').props.onClick();
  label(h.render(), '覆盖规则主机').props.onChange({ target: { value: 'example.com' } });
  await button(h.render(), '添加').props.onClick();
  assert.deepEqual(plain(h.context.settings.network.routes), { 'example.com': 'direct' });
  label(h.render(), '删除规则 example.com').props.onClick();
  await settle();
  assert.deepEqual(plain(h.context.settings.network.routes), {});
  assert.ok(h.calls.some((call) => call.clear === 'example.com'));
});

test('线路检查只发送目标 URL，离线时禁用操作', async () => {
  const h = harness();
  button(h.render(), '高级网络诊断').props.onClick();
  await settle();
  label(h.render(), '线路检查地址').props.onChange({ target: { value: 'https://example.org/page' } });
  await button(h.render(), '检查').props.onClick();
  assert.ok(h.calls.some((call) => call.check === 'https://example.org/page'));
  h.setDisabled(true);
  assert.equal(button(h.render(), '检查').props.disabled, true);
  assert.equal(button(h.render(), '添加').props.disabled, true);
  assert.equal(find(label(h.render(), '代理地址'), (node) => node.type === 'field').props.disabled, true);
});
