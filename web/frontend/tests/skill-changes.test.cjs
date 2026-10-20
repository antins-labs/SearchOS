/* eslint-disable @typescript-eslint/no-require-imports -- 用真实 React 渲染验证技能变化卡片。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

async function render(data, { id = "generation", base = "", error = "" } = {}) {
  const markdown = await import("react-markdown");
  const gfm = await import("remark-gfm");
  const exports = {};
  const dependencies = {
    "next/link": ({ children, ...props }) => React.createElement("a", props, children),
    "react-markdown": { __esModule: true, ...markdown },
    "remark-gfm": { __esModule: true, ...gfm },
    "@/hooks/useSkillGeneration": { useSkillGeneration: () => ({ data, error, retry() {} }) },
    "@/hooks/useWorkspaceBase": { useWorkspaceBase: () => base },
    "@/components/settings/SettingsProvider": { useSettings: () => ({ uiPrefs: { language: "zh" } }) },
  };
  const source = fs.readFileSync(path.join(__dirname, "../src/components/conversation/SkillChanges.tsx"), "utf8");
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, { exports, require: (name) => name in dependencies ? dependencies[name] : require(name) });
  return renderToStaticMarkup(React.createElement(exports.default, { sessionId: "session", generationId: id }));
}

const item = (action, status = "installed") => ({ name: `${action}-method`, category: "strategy", action, status, description: "可复用方法", reason: "补充分页核验", body: "# 本次技能\n保存的说明。" });

test("仅开启生成且有本轮记录时展示卡片，旧会话保持兼容", async () => {
  assert.equal(await render(null, { id: null }), "");
  assert.match(await render(null), /正在整理可复用的技能/);
});

test("新增、更新和失败分开统计，失败不能冒充已入库", async () => {
  const html = await render({ status: "completed", items: [item("create"), item("update"), { ...item("create", "validation_failed"), name: "failed-method", body: undefined }] });
  assert.match(html, /已新增 1 个技能，更新 1 个技能/);
  assert.match(html, /未通过验证，未修改技能库/);
  assert.match(html, /变化原因：.*补充分页核验/);
  assert.equal((html.match(/查看本次版本/g) || []).length, 2);
});

test("完成且无变化、生成失败和进程中断保留不同语义", async () => {
  assert.match(await render({ status: "completed", items: [] }), /本轮未发现需要新增或更新的技能/);
  assert.match(await render({ status: "error", items: [] }), /技能生成未完成，搜索结果已保留/);
  assert.match(await render({ status: "interrupted", items: [item("create"), item("update", "running")] }), /技能生成已中断/);
  assert.doesNotMatch(await render({ status: "interrupted", items: [item("update", "running")] }), /生成中/);
});

test("mobile 技能库链接留在 mobile，正文预览不加载远程图片或相对脚本链接", async () => {
  const html = await render({ status: "completed", items: [{ ...item("create"), body: "[脚本](scripts/run.py) ![图](https://example.org/tracker) [官网](https://example.org)" }] }, { base: "/m" });
  assert.match(html, /href="\/m\/skills"/);
  assert.doesNotMatch(html, /href="scripts\/|<img/);
  assert.match(html, /rel="noopener noreferrer"/);
});

test("读取故障保留已收到的技能变化并提供重试", async () => {
  const html = await render({ status: "running", items: [item("create")] }, { error: "offline" });
  assert.match(html, /暂时无法同步技能变化/);
  assert.match(html, /立即重试/);
  assert.match(html, /create-method/);
});
