/* eslint-disable @typescript-eslint/no-require-imports -- Node 测试直接加载配置组件。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");

function load(file, customRequire = require) {
  const source = fs.readFileSync(path.join(__dirname, "../src", file), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, { exports, require: customRequire });
  return exports;
}

const helpers = load("lib/modelPurposes.ts");
const plain = (value) => JSON.parse(JSON.stringify(value));

function fixture() {
  const purpose = (role, allocation) => ({ role, allocation, label: { zh: role, en: role },
    description: { zh: "用途说明", en: "Purpose description" }, guidance: { zh: "使用条件", en: "Usage guidance" } });
  return {
    profiles: { main: { api_key_set: true, api_key_env: "MAIN_KEY", model: "main-model" },
      fast: { api_key_set: true, api_key_env: "FAST_KEY", model: "fast-model" },
      vision: { api_key_set: true, api_key_env: "VISION_KEY", model: "vision-model" } },
    roles: { orchestrator: "main", judge: "fast", extraction: "main", local_recap: "main", local_vision: "vision", reformat: "fast" },
    role_overrides: {},
    purpose_groups: [
      { id: "research", label: { zh: "研究执行", en: "Research" }, purposes: [purpose("orchestrator", "main"), purpose("judge", "main"), purpose("extraction", "text")] },
      { id: "content", label: { zh: "内容处理", en: "Content" }, purposes: [purpose("local_recap", "text"), purpose("local_vision", "vision")] },
      { id: "evaluation", label: { zh: "评测", en: "Evaluation" }, purposes: [purpose("reformat", null)] },
    ],
  };
}

test("批量分配使用所选模型，保留评测且不改写输入", () => {
  const models = fixture();
  const before = JSON.stringify(models);
  const changes = helpers.planModelAllocation(models, { main: "main", text: "fast", vision: "vision" });
  assert.deepEqual(plain(changes), [
    { role: "judge", before: "fast", after: "main" },
    { role: "extraction", before: "main", after: "fast" },
    { role: "local_recap", before: "main", after: "fast" },
  ]);
  assert.equal(JSON.stringify(models), before);
});

test("所选模型能覆盖缺失用途，选择不完整或无效时不能分配", () => {
  const models = fixture();
  delete models.roles.local_recap;
  models.roles.local_vision = "main";
  const changes = plain(helpers.planModelAllocation(models, { main: "main", text: "main", vision: "vision" }));
  assert.ok(changes.some((change) => change.role === "local_recap" && change.before === "" && change.after === "main"));
  assert.ok(changes.some((change) => change.role === "local_vision" && change.after === "vision"));
  for (const field of ["main", "text", "vision"]) {
    for (const invalid of ["", "deleted"]) {
      assert.deepEqual(plain(helpers.planModelAllocation(models, { main: "main", text: "fast", vision: "vision", [field]: invalid })), []);
    }
  }
});

test("绑定缺失、模型缺失和密钥缺失均可见，未测试不伪装为连接通过", () => {
  const models = fixture();
  assert.equal(helpers.modelBindingIssue(models, "missing", "zh"), "尚未绑定模型");
  models.roles.judge = "deleted";
  assert.match(helpers.modelBindingIssue(models, "judge", "zh"), /不存在/);
  models.profiles.main.api_key_set = false;
  assert.match(helpers.modelBindingIssue(models, "orchestrator", "zh"), /MAIN_KEY/);
  assert.equal(helpers.modelBindingIssue(models, "local_vision", "en"), null);
});

function harness(file, initialModels = fixture()) {
  const states = [];
  let index = 0;
  const calls = [];
  const context = { settings: { models: initialModels }, status: "ready", uiPrefs: { language: "zh" }, notify() {},
    async mutate(args) {
      const result = await args.call();
      context.settings = args.merge(context.settings, result);
      return result;
    } };
  const component = load(file, (name) => {
    if (name === "react") return { ...React, useId: () => "purposes", useState(initial) {
      const slot = index++;
      if (!(slot in states)) states[slot] = typeof initial === "function" ? initial() : initial;
      return [states[slot], (value) => { states[slot] = typeof value === "function" ? value(states[slot]) : value; }];
    } };
    if (name === "@/components/settings/SettingsProvider") return { useSettings: () => context };
    if (name === "@/components/ui/Select") return { __esModule: true, default: "test-select" };
    if (name === "@/lib/modelPurposes") return helpers;
    if (name === "@/lib/api") return { async putRoles(bindings) {
      calls.push(plain(bindings));
      return { roles: { ...context.settings.models.roles, ...bindings }, role_overrides: { ...bindings }, warnings: [] };
    }, async testProvider(role) { calls.push(role); return { ok: true, role, provider: "test", model: "main-model", latency_ms: 1 }; } };
    return require(name);
  }).default;
  return { context, calls, render() { index = 0; return component(); } };
}

function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of React.Children.toArray(node.props?.children)) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}
const button = (tree, text) => find(tree, (node) => node.type === "button" && React.Children.toArray(node.props.children).includes(text));

test("旧后端未返回用途目录时，配置和诊断仍可打开", () => {
  const models = fixture();
  delete models.purpose_groups;
  models.roles.skill_runtime = "main";
  const bindings = harness("components/settings/models/ModelPurposeBindings.tsx", models);
  const diagnostics = harness("components/settings/diagnostics/ProviderDiagnosticPanel.tsx", models);
  const tree = bindings.render();
  assert.ok(find(tree, (node) => node.props?.ariaLabel === "orchestrator使用的模型"));
  const select = find(diagnostics.render(), (node) => node.props?.ariaLabel === "测试用途");
  assert.equal(select.props.options.length, 6);
  assert.equal(select.props.options.some((option) => option.value === "skill_runtime"), false);
  assert.deepEqual(plain(helpers.planModelAllocation(models, { main: "main", text: "fast", vision: "vision" })), []);
  assert.equal(button(tree, "预览分配"), null);
  for (const catalog of [null, []]) {
    models.purpose_groups = catalog;
    assert.doesNotThrow(() => bindings.render());
    assert.doesNotThrow(() => diagnostics.render());
  }
  bindings.context.settings.models = fixture();
  assert.ok(button(bindings.render(), "预览分配"));
});

test("快速分配先预览，再以单次请求保存，预览本身不写入", async () => {
  const h = harness("components/settings/models/ModelPurposeBindings.tsx");
  let tree = h.render();
  find(tree, (node) => node.props?.ariaLabel === "高频文本模型").props.onChange("fast");
  tree = h.render();
  button(tree, "预览分配").props.onClick();
  assert.equal(h.calls.length, 0);
  tree = h.render();
  button(tree, "应用分配").props.onClick();
  await new Promise(setImmediate);
  assert.deepEqual(h.calls, [{ judge: "main", extraction: "fast", local_recap: "fast" }]);
  assert.equal(h.context.settings.models.roles.local_vision, "vision");
  assert.equal(h.context.settings.models.roles.reformat, "fast");
  assert.equal(button(h.render(), "应用分配"), null);
});

test("配置变化使已有预览失效，旧应用按钮不会写入", () => {
  const h = harness("components/settings/models/ModelPurposeBindings.tsx");
  button(h.render(), "预览分配").props.onClick();
  h.context.settings.models.profiles.main.model = "changed-model";
  const apply = button(h.render(), "应用分配");
  assert.equal(apply.props.disabled, true);
  apply.props.onClick();
  assert.equal(h.calls.length, 0);
});

test("连接测试覆盖目录用途，模型变化后不再展示旧成功结果", async () => {
  const h = harness("components/settings/diagnostics/ProviderDiagnosticPanel.tsx");
  let tree = h.render();
  const select = find(tree, (node) => node.props?.ariaLabel === "测试用途");
  assert.equal(select.props.options.length, 6);
  await button(tree, "测试").props.onClick();
  tree = h.render();
  assert.ok(find(tree, (node) => React.Children.toArray(node.props?.children).includes("文本连接通过")));
  h.context.settings.models.profiles.main.model = "changed-model";
  tree = h.render();
  assert.equal(find(tree, (node) => React.Children.toArray(node.props?.children).includes("文本连接通过")), null);
  await button(tree, "测试").props.onClick();
  assert.ok(find(h.render(), (node) => React.Children.toArray(node.props?.children).includes("文本连接通过")));
  // 换密钥时 API 只返回是否已配置；即使内容相同，新设置快照也使旧诊断失效。
  h.context.settings.models = plain(h.context.settings.models);
  assert.equal(find(h.render(), (node) => React.Children.toArray(node.props?.children).includes("文本连接通过")), null);
});
