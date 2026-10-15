/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const api = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, "../src/lib/mobileReportPreview.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { exports: api, URL });

test("phone report preview excludes legacy empty placeholders, table syntax and source appendix", () => {
  const report = "# test query\n\n_(empty body)_\n## 数据对比表\n| 名称 | 时间 |\n|---|---|\n| A | 10:00 |\n## 信息来源\n1. https://example.com";
  assert.equal(api.mobileReportExcerpt(report, "test query"), "");
});
test("phone report preview retains prose labels but does not expose Markdown URL syntax", () => {
  assert.equal(api.mobileReportExcerpt("# Query\n**主要发现**\n见[官方说明](https://example.com)。\n## Sources\nOther", "Query"), "主要发现\n见官方说明。");
});
test("phone report preview is bounded without modifying the original report", () => {
  const report = "甲".repeat(400);
  assert.equal(api.mobileReportExcerpt(report, "q").length, 281);
  assert.equal(report.length, 400);
});

test("all 16 entries retain independent fields and exact table/row identity", () => {
  const entities = Array.from({ length: 16 }, (_, i) => `item.${i}/name`);
  const table = { table_id: "news", entities, attributes: ["标题", "事件概述", "来源URL", "发布时间", "重要性原因"] };
  const cells = {};
  for (const entity of entities) {
    cells[`news/${entity}.标题`] = { value: `标题 ${entity}`, status: "filled" };
    cells[`news/${entity}.事件概述`] = { value: ["第一段", "第二段"], status: "filled" };
    cells[`news/${entity}.来源URL`] = { value: "[原文](https://example.com/article)", status: "filled" };
  }
  cells[`other/${entities[0]}.事件概述`] = { value: "another table", status: "filled" };
  cells[`news/${entities[15]}.重要性原因`] = { value: "不同说法", status: "uncertain", has_conflict: true };
  const rows = api.reportRows(table, cells);
  assert.equal(rows.length, 16);
  assert.equal(rows[15].title, `标题 ${entities[15]}`);
  assert.equal(rows[0].summary, "第一段\n\n第二段");
  assert.equal(rows[0].sources[0], "https://example.com/article");
  assert.equal(rows[0].fields.find(field => field.name === "发布时间").status, "missing");
  assert.equal(rows[15].needsReview, true);
});

test("source actions accept web and local references but reject executable or credential URLs", () => {
  const links = api.reportSourceLinks("javascript:alert(1) data:text/html,xx https://user:pass@example.com/a https://example.com/a。 local://library/doc https://example.com/a");
  assert.deepEqual(Array.from(links), ["https://example.com/a", "local://library/doc"]);
});

test("generic schemas and missing values do not become invented summaries", () => {
  const rows = api.reportRows({ table_id: "products", entities: ["A"], attributes: ["价格", "来源"] }, {
    "products/A.价格": { value: "旧数据", status: "missing" },
    "products/A.来源": { value: "javascript:alert(1)", status: "filled" },
  });
  assert.equal(rows[0].title, "A");
  assert.equal(rows[0].summary, "");
  assert.equal(rows[0].sources.length, 0);
});
