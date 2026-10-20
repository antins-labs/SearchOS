/* eslint-disable @typescript-eslint/no-require-imports -- 渲染展开后的创建记录，核对实际恢复入口。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function render(request, result, extra = {}) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/components/skills/SkillCreationHistory.tsx'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(compiled + '\nexports.JobCard = JobCard;', { exports, require(name) {
    if (name === 'react') return { ...React, useState: (initial) => React.useState(initial === false ? true : initial) };
    if (name === './SkillDraftEditor') return { default: () => null };
    return require(name);
  } });
  const job = { id: 'job', input: { site: 'https://example.com/news', text: '' }, status: 'failed',
    stage: 'done', error: '', created_at: '2026-10-19T07:26:00Z', requests: [request], results: [result], ...extra };
  return renderToStaticMarkup(React.createElement(exports.JobCard, { job, zh: true, disabled: false,
    repairing: [], managing: false, selected: false, working: false,
    onSelect() {}, onAction() {}, onRetry() {}, onResume() {} }));
}

const request = { name: 'example-com', category: 'access', description: '读取新闻' };

test('站点能力规划阶段不提前显示生成与验证', () => {
  const planning = render(request, {}, { status: 'running', stage: 'site_intent', results: [] });
  assert.match(planning, /正在规划站点能力…/);
  assert.doesNotMatch(planning, /正在生成与验证/);
  const building = render(request, {}, { status: 'running', stage: 'pipeline', results: [] });
  assert.match(building, /正在生成与验证/);
  assert.doesNotMatch(building, /正在规划站点能力/);
});

test('需求规划失败可复用研究继续创建，没有草稿时不显示编辑入口', () => {
  const html = render({ ...request, has_draft: false, has_site_session: true, can_resume: true },
    { status: 'error', failure_stage: 'site_intent', error: 'inputs must map parameter names to descriptions' });
  assert.match(html, /需求规划未完成/);
  assert.match(html, /脚本生成尚未开始/);
  assert.match(html, /继续创建<\/button>/);
  assert.doesNotMatch(html, /查看 \/ 编辑草稿|重新分析并生成|执行错误/);
});

test('历史规划失败显示准确阶段，研究恢复记录明确复用已有研究', () => {
  const html = render({ ...request, has_site_session: true, can_resume: true },
    { status: 'error', error: 'site intent call budget exhausted without a valid response' },
    { resume_of: { job_id: 'parent', index: 0 }, resume_kind: 'site_session' });
  assert.match(html, /需求规划未完成/);
  assert.match(html, /复用已保存的站点研究/);
  assert.doesNotMatch(html, /使用原有草稿继续验证/);
});

test('已有草稿继续编辑续修，已入库结果不再显示恢复按钮', () => {
  const draft = render({ ...request, has_draft: true }, { status: 'build_failed' });
  assert.match(draft, /查看 \/ 编辑草稿/);
  assert.match(draft, /继续修复<\/button>/);
  const installed = render({ ...request, has_draft: true, has_site_session: true, can_resume: false },
    { status: 'installed' }, { status: 'completed' });
  assert.doesNotMatch(installed, /继续修复<\/button>|继续创建<\/button>/);
});

test('没有可恢复状态时保留重新分析入口', () => {
  const html = render({ ...request, has_draft: false, has_site_session: false, can_resume: false }, { status: 'error' });
  assert.match(html, /重新分析并生成/);
  assert.doesNotMatch(html, /继续创建<\/button>/);
});
