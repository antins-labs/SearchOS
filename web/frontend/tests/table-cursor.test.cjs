/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function load() {
  const source = fs.readFileSync(path.join(__dirname, "../src/lib/tableCursor.ts"), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, {
    exports,
    atob: (value) => Buffer.from(value, "base64").toString("utf8"),
  });
  return exports;
}

test("decodeTableCursor expands urlsafe pagination tokens", () => {
  const { decodeTableCursor, prettyToolPayload } = load();
  const payload = {
    version: 2,
    query: ["products", "all", null, "", false],
    after: '["茅台","国窖1573·国礼酒"]',
  };
  const raw = Buffer.from(JSON.stringify(payload), "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const decoded = decodeTableCursor(raw);
  assert.equal(decoded.version, 2);
  assert.equal(decoded.table_id, "products");
  assert.equal(decoded.status, "all");
  assert.equal(decoded.row, null);
  assert.equal(decoded.attribute, "");
  assert.equal(decoded.unassigned_only, false);
  assert.equal(decoded.after, payload.after);
  const pretty = prettyToolPayload(JSON.stringify({
    table_id: "products",
    cursor: raw,
    limit: 78,
    next_cursor: raw,
  }));
  assert.match(pretty, /"decoded"/);
  assert.match(pretty, /茅台/);
  assert.match(pretty, /"raw"/);
  assert.ok(!pretty.includes(`"cursor": "${raw}`));
});

test("prettyToolPayload leaves unrelated payloads alone", () => {
  const { prettyToolPayload } = load();
  assert.equal(
    prettyToolPayload('{"query":"hello","cursor":""}'),
    '{\n  "query": "hello",\n  "cursor": ""\n}',
  );
  assert.equal(prettyToolPayload("not-json"), "not-json");
});
