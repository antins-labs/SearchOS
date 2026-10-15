/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const api = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, "../src/lib/hostStatus.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: api });
const healthy = { scheduler_running: true, instance_id: "first" };

test("old successful responses cannot keep a sleeping phone green indefinitely", () => {
  const online = api.receivedHost(api.INITIAL_HOST, healthy, 1000);
  assert.equal(online.phase, "online");
  assert.equal(online.notice, null);
  const stale = api.freshHost(online, 30000);
  assert.equal(stale.phase, "checking");
  assert.equal(stale.lastSeen, 1000);
  assert.equal(api.receivedHost(stale, healthy, 31000).notice, "reconnected");
});
test("host reachable is distinct from scheduler healthy, recovery and process restart", () => {
  const online = api.receivedHost(api.INITIAL_HOST, healthy, 1000);
  const degraded = api.receivedHost(online, { ...healthy, scheduler_running: false }, 2000);
  assert.equal(degraded.phase, "degraded");
  const reconnected = api.receivedHost({ ...degraded, phase: "unreachable" }, healthy, 3000);
  assert.equal(reconnected.notice, "reconnected");
  const restarted = api.receivedHost(reconnected, { ...healthy, instance_id: "second" }, 4000);
  assert.equal(restarted.notice, "restarted");
  assert.match(api.hostMessage({ phase: "unreachable" }), /暂时无法连接/);
  assert.equal(api.uptimeLabel(90061), "1 天 1 小时");
});
