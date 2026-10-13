/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const api = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, "../src/lib/sourceSelection.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: api });
const selection = (...args) => JSON.parse(JSON.stringify(api.buildSourceSelection(...args)));

test("Hybrid 未勾选文件时明确传递当前库范围", () => {
  assert.deepEqual(selection("hybrid", "selected-library", []), { mode: "hybrid", local: {
    library_id: "selected-library", selection: "library", document_ids: [], model_access: true,
  } });
});
test("具体文档限制范围，Web 和无库 Hybrid 不授予库访问", () => {
  assert.equal(selection("hybrid", "selected-library", ["doc"]).local.selection, "documents");
  assert.deepEqual(selection("web", "selected-library", ["doc"]), {mode:"web"});
  assert.deepEqual(selection("hybrid", null, []), {mode:"hybrid"});
  assert.equal(api.buildSourceSelection("local", null, []), undefined);
});
