/* eslint-disable @typescript-eslint/no-require-imports -- 渲染展开后的创建记录，核对实际恢复入口。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function render(request, result, extra = {}, zh = true) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/components/skills/SkillCreationHistory.tsx'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(compiled + '\nexports.JobCard = JobCard;', { exports, require(name) {
    if (name === 'react') return { ...React, useState: (initial) => React.useState(initial === false ? true : initial) };
    if (name === './SkillDraftEditor') return { default: () => null };
    if (name === './SkillUserAction') {
      const nested = { exports: {}, require(name) { return name === '@/lib/api' ? {} : require(name); } };
      const source = fs.readFileSync(path.join(__dirname, '../src/components/skills/SkillUserAction.tsx'), 'utf8');
      vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
      } }).outputText, nested);
      return nested.exports;
    }
    return require(name);
  } });
  const job = { id: 'job', input: { site: 'https://example.com/news', text: '' }, status: 'failed',
    stage: 'done', error: '', created_at: '2026-10-19T07:26:00Z', requests: [request], results: [result], ...extra };
  return renderToStaticMarkup(React.createElement(exports.JobCard, { job, zh, disabled: false,
    repairing: [], managing: false, selected: false, working: false,
    onSelect() {}, onAction() {}, onRetry() {}, onResume() {} }));
}

const request = { name: 'example-com', category: 'access', description: '读取新闻' };

test('刷新等待记录后仍展示操作卡片，已处理操作禁止重复提交', () => {
  const extra = { status: 'waiting_user', user_action: { id: 'op-1', state: 'pending', kind: 'login',
    message: '请扫码登录', url: 'https://example.com/login' } };
  const page = render(request, {}, extra);
  for (const label of ['等待用户操作', '请扫码登录', '打开浏览器', '已完成，继续', '跳过此次操作', '停止创建']) {
    assert.ok(page.includes(label));
  }
  const handled = render(request, {}, { ...extra, user_action: { ...extra.user_action, state: 'continue' } });
  assert.match(handled, /disabled=""[^>]*>已完成，继续/);
});

test('已入库且有受阻能力时显示显式补验入口', () => {
  const page = render({ ...request, can_revalidate: true }, { status: 'installed', name: 'example-com' }, { status: 'completed' });
  assert.match(page, /补验受阻能力/);
});

test('站点能力规划阶段不提前显示生成与验证', () => {
  const planning = render(request, {}, { status: 'running', stage: 'site_intent', results: [] });
  assert.match(planning, /正在规划站点能力…/);
  assert.doesNotMatch(planning, /正在生成技能|正在独立验证技能/);
  const building = render(request, {}, { status: 'running', stage: 'pipeline', results: [] });
  assert.match(building, /正在生成技能/);
  assert.doesNotMatch(building, /正在规划站点能力/);
});

test('独立验证与返回修复展示准确阶段，中英文一致', () => {
  const validating = render(request, {}, { status: 'running', stage: 'access_validation', results: [] });
  assert.match(validating, /正在独立验证技能…/);
  assert.doesNotMatch(validating, /正在生成技能/);
  const english = render(request, {}, { status: 'running', stage: 'access_validation', results: [] }, false);
  assert.match(english, /Independently validating the skill…/);
  const repairing = render(request, {}, { status: 'running', stage: 'pipeline', results: [] });
  assert.match(repairing, /正在生成技能/);
  assert.doesNotMatch(repairing, /正在独立验证技能/);
});

test('独立验收失败保留阶段与草稿续修入口', () => {
  const result = { status: 'validation_failed', failure_stage: 'access_validation', error: '来源内容不一致' };
  const html = render({ ...request, has_draft: true }, result);
  assert.match(html, /独立验证未通过/);
  assert.match(html, /来源内容不一致/);
  assert.match(html, /继续修复<\/button>/);
  assert.doesNotMatch(html, /需求规划未完成|脚本生成尚未开始/);
  const english = render({ ...request, has_draft: true }, result, {}, false);
  assert.match(english, /Independent validation failed/);
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

test('已入库结果显示各能力状态、检查与原因，不把入库视为全部通过', () => {
  const result = { status: 'installed', validation_status: 'partial', capability_results: {
    article_detail: { status: 'available', deterministic: 'passed', semantic: 'passed', reason: '正文与来源一致' },
    site_search: { status: 'unavailable', deterministic: 'passed', semantic: 'failed', reason: '登录页被当成搜索结果' },
    news_archive: { status: 'incomplete', deterministic: 'incomplete', semantic: 'incomplete', reason: '尚未实现' },
  } };
  const html = render(request, result, { status: 'completed' });
  assert.match(html, /已入库/);
  assert.match(html, /aria-label="能力验收结果"/);
  assert.match(html, /article_detail<\/span><span[^>]*>可用/);
  assert.match(html, /site_search<\/span><span[^>]*>不可用/);
  assert.match(html, /news_archive<\/span><span[^>]*>未完成/);
  assert.match(html, /执行检查：通过 · 内容核验：失败/);
  for (const reason of ['正文与来源一致', '登录页被当成搜索结果', '尚未实现']) assert.ok(html.includes(reason));
  const english = render(request, result, { status: 'completed' }, false);
  assert.match(english, /aria-label="Capability validation results"/);
  for (const status of ['Available', 'Unavailable', 'Incomplete']) assert.ok(english.includes(`>${status}<`));
  assert.match(english, /Execution: Passed · Content: Failed/);
});

test('旧记录与空能力结果保持原显示，不推断未记录的能力状态', () => {
  const legacy = render(request, { status: 'installed' }, { status: 'completed' });
  const empty = render(request, { status: 'installed', capability_results: {} }, { status: 'completed' });
  assert.equal(empty, legacy);
  assert.doesNotMatch(legacy, /能力验收结果|执行检查|内容核验/);
});
