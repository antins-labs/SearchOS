/* eslint-disable @typescript-eslint/no-require-imports -- Node test renders TSX components directly. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function transpile(relativePath, context = {}) {
  const source = fs.readFileSync(path.join(__dirname, relativePath), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText, { exports, ...context });
  return exports;
}

test("tool detail keeps parameters and output as equal shrinkable columns", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const component = transpile("../src/components/workbench/ToolCallDetailDialog.tsx", {
    document: { body: {} },
    navigator: { clipboard: { writeText: async () => {} } },
    window: { setTimeout },
    require(name) {
      if (name === "react-dom") return { createPortal: (element) => element };
      if (name === "@/hooks/useDialogFocus") return { __esModule: true, default: () => {} };
      return require(name);
    },
  }).default;
  const longUrl = `https://example.com/${"long-segment".repeat(80)}`;
  const html = renderToStaticMarkup(React.createElement(component, {
    detail: { tool: "view", arguments: JSON.stringify({ url: longUrl }), output: longUrl },
    onClose() {},
  }));

  assert.equal((html.match(/md:basis-1\/2/g) || []).length, 2);
  assert.equal((html.match(/min-w-0/g) || []).length >= 3, true);
  assert.equal((html.match(/break-all/g) || []).length, 2);
});

test("待处理追问显示引导和删除操作，空队列不占空间", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const component = transpile("../src/components/shell/PendingFollowUps.tsx", { require }).default;
  const queue = { pending: [], working: new Set(), guide() {}, remove() {} };
  assert.equal(renderToStaticMarkup(React.createElement(component, { queue, running: true })), "");
  queue.pending = [{ id: "m1", text: "查询相关论文", mode: "after_tool", status: "queued" }];
  const html = renderToStaticMarkup(React.createElement(component, { queue, running: true }));
  assert.match(html, /查询相关论文/);
  assert.match(html, /立即引导当前运行/);
  assert.match(html, /删除待处理追问/);
  assert.equal((html.match(/<button/g) || []).length, 2);
  assert.doesNotMatch(html, /<select/);
});
