/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const api = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, "../src/lib/mobileSources.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { exports: api });
const docs = [{document_id:"ready",searchable:true},{document_id:"pending",searchable:false}];
const select = (mode, libraryId, ids) => api.mobileSourceSelection(mode, libraryId, docs, ids);

test("mobile cancellation, missing library and unready selection never broaden to library access", () => {
  for (const mode of ["local", "hybrid"]) {
    assert.equal(select(mode, "lib", []), undefined);
    assert.equal(select(mode, null, ["ready"]), undefined);
    assert.equal(select(mode, "lib", ["pending", "removed"]), undefined);
  }
});
test("mobile source confirmation preserves requested mode and only authorizes current searchable IDs", () => {
  for (const mode of ["local", "hybrid"]) {
    assert.deepEqual(JSON.parse(JSON.stringify(select(mode, "lib", ["ready", "pending", "ready", "other-library-doc"]))), {
      mode, local: { library_id: "lib", document_ids: ["ready"], selection: "documents", model_access: true },
    });
  }
});
test("switching mobile source to web strips all local authorization", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(select("web", "lib", ["ready"]))), {mode:"web"});
});
