/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function loadEvidenceList() {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/components/evidence/EvidenceList.tsx"),
    "utf8",
  );
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText, {
    exports,
    URL,
    require(name) {
      if (name === "@/lib/api") return {};
      if (name === "@/lib/localCitations") return { localCitationLabels: () => ({}) };
      return require(name);
    },
  });
  return exports;
}

test("知识库保存按来源页面分组，而不是按证据分组", () => {
  const { groupEvidenceBySource } = loadEvidenceList();
  const pages = groupEvidenceBySource([
    { source: "https://example.com/report?a=1", page_id: "page1", created_at: 2 },
    { source: "https://example.com/report?a=1", page_id: "page1", created_at: 3 },
    { source: "https://example.com/other", page_id: "page2", created_at: 1 },
    { source: "local://library/document" },
  ]);

  assert.deepEqual(JSON.parse(JSON.stringify(pages)), [
    {
      url: "https://example.com/other",
      pageId: "page2",
      evidenceCount: 1,
      capturedAt: 1,
    },
    {
      url: "https://example.com/report?a=1",
      pageId: "page1",
      evidenceCount: 2,
      capturedAt: 3,
    },
  ]);
});

test("保存页面区域独立于证据视图，证据数不被路径挤掉", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/components/evidence/EvidenceList.tsx"),
    "utf8",
  );
  const savePanel = source.indexOf("保存来源页面");
  const tabs = source.indexOf('role="tablist"', savePanel);

  assert.ok(savePanel >= 0 && tabs > savePanel);
  assert.match(source, /shrink-0 text-\[9\.5px\] text-ink-faint">关联 \{source\.evidenceCount\} 条证据/);
});
