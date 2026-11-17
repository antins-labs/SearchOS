/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function load(name) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, `../src/lib/${name}.ts`), "utf8");
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports, require: (name) => {
    assert.equal(name, "./localCopy");
    return load("localCopy");
  } });
  return exports;
}

const { documentIndexProgress, documentStatusLabel, uploadStatusLabel } = load("localPresentation");
const { localCopy: copy } = load("localCopy");
const document = (recap_status, job) => ({
  recap_status, searchable: true, catalog_status: "pending",
  recap_segments_completed: 2, recap_segments_total: 5,
  index_job: job && { status: job },
});

test("待处理、部分完成与取消状态分别展示", () => {
  assert.equal(documentIndexProgress(document("pending")).label, copy.status.recapPending);
  assert.equal(documentIndexProgress(document("partial")).label, copy.status.recapPartial);
  assert.equal(documentIndexProgress(document("pending", "cancelled")).label, copy.status.recapCancelled);
});

test("重试时使用当前任务进度，保留已完成摘要的状态", () => {
  const retry = document("failed", "running");
  retry.index_job.recap_segments_completed = 1;
  retry.index_job.recap_segments_total = 4;
  const progress = documentIndexProgress(retry);
  assert.equal(progress.percent, 25);
  assert.equal(progress.failed, false);
  assert.equal(progress.label, copy.status.indexing);
  assert.equal(documentIndexProgress(document("ready", "failed")).label, copy.status.recapReady);
  assert.equal(documentIndexProgress(document("ready", "cancelled")).label, copy.status.recapReady);
});

test("目录处理失败时仍能区分正文可用性", () => {
  const available = document("ready", "failed");
  assert.equal(documentStatusLabel(available), copy.status.indexFailed);
  assert.equal(documentStatusLabel({ ...available, searchable: false, parse_status: "failed" }), copy.status.parseFailed);
  assert.equal(uploadStatusLabel({ status: "index_cancelled", progress: 100 }), copy.status.cancelled);
  assert.equal(uploadStatusLabel({ status: "ready", progress: 100, cached: true }), copy.status.cached);
});
