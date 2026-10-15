/* eslint-disable @typescript-eslint/no-require-imports -- Node 测试使用 CommonJS 加载源码。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const read = (file) => fs.readFileSync(path.join(__dirname, "../src", file), "utf8");

test("local source picker closes outside and supports keyboard disclosure semantics", () => {
  const source = read("components/local/LocalSourceControl.tsx");
  assert.match(source, /document\.addEventListener\("pointerdown"/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /aria-expanded=\{open\}/);
  assert.match(source, /aria-controls=\{panelId\}/);
  assert.match(source, /aria-pressed=\{selected\}/);
});

test("composer keeps transient source, schema and override panels mutually exclusive", () => {
  const source = read("components/shell/Composer.tsx");
  assert.match(source, /const \[sourceOpen, setSourceOpen\] = useState\(false\)/);
  assert.match(source, /open=\{sourceOpen\}/);
  assert.match(source, /setShowSchema\(false\);\s*setShowOverrides\(false\);/);
  assert.match(source, /setSourceOpen\(false\);\s*setShowOverrides\(false\);/);
  assert.match(source, /setSourceOpen\(false\);\s*setShowSchema\(false\);/);
});

test("local source picker provides scalable selection controls", () => {
  const source = read("components/local/LocalSourceControl.tsx");
  assert.match(source, /placeholder="搜索资料"/);
  assert.match(source, />全选可用</);
  assert.match(source, />清空</);
  assert.match(source, /没有匹配的资料/);
});

test("adding a file from Web enters Local mode and mode buttons expose selection", () => {
  const source = read("components/local/LocalSourceControl.tsx");
  assert.match(source, /if \(controller\.mode === "web"\) controller\.setMode\("local"\)/);
  assert.equal((source.match(/aria-pressed=\{controller\.mode ===/g) || []).length, 3);
  assert.match(source, /未选文档时检索整个当前知识库/);
});

test("Local mode submits an explicit library scope when no document is selected", () => {
  const hook = read("hooks/useLocalLibrary.ts");
  const composer = read("components/shell/Composer.tsx");
  const landing = read("components/conversation/Landing.tsx");
  assert.match(hook, /buildSourceSelection\(mode, libraryId, selectedDocumentIds\)/);
  assert.match(composer, /sources: localLibrary\.selection/);
  assert.match(landing, /sources: localLibrary\.selection/);
});

test("run override toggle does not race its outside-click listener", () => {
  const composer = read("components/shell/Composer.tsx");
  const popover = read("components/settings/RunOverridesPopover.tsx");
  assert.match(composer, /data-run-overrides-toggle/);
  assert.match(popover, /closest\("\[data-run-overrides-toggle\]"\)/);
});

test("history action menu closes outside and on Escape", () => {
  const source = read("components/shell/HistoryRail.tsx");
  assert.match(source, /data-history-menu-owner/);
  assert.match(source, /document\.addEventListener\("pointerdown"/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /aria-haspopup="menu"/);
  assert.match(source, /role="menu"/);
});

test("landing suggestions preserve the selected source mode", () => {
  const source = read("components/conversation/Landing.tsx");
  assert.match(source, /onSubmit\(s\.text, \{ sources: localLibrary\.selection \}\)/);
  assert.match(source, /disabled=\{localLibrary\.mode === "local" && !localLibrary\.selection\}/);
});

test("composer placeholder explains the active source scope", () => {
  const source = read("components/shell/Composer.tsx");
  assert.match(source, /询问所选的.*份资料/);
  assert.match(source, /检索当前知识库并回答/);
  assert.match(source, /结合网络与.*份资料提问/);
  assert.match(source, /搜索网络并回答/);
});

test("local source preview behaves as a keyboard-safe modal", () => {
  const source = read("components/sources/SourcePanel.tsx");
  assert.match(source, /useDialogFocus\(\{ containerRef: dialogRef, initialFocusRef: closeRef, onClose \}\)/);
  assert.match(source, /role="dialog"/);
  assert.match(source, /aria-modal="true"/);
  assert.match(source, /onMouseDown=\{onClose\}/);
  assert.match(source, /onMouseDown=\{\(event\) => event\.stopPropagation\(\)\}/);
});

test("mobile navigation closes on Escape and restores trigger focus", () => {
  const source = read("components/research/ResearchWorkspace.tsx");
  assert.match(source, /const closeMobileRail = useCallback/);
  assert.match(source, /useDialogFocus\(\{/);
  assert.match(read("hooks/useDialogFocus.ts"), /event\.key === "Escape"/);
  assert.match(source, /mobileRailTriggerRef\.current\?\.focus\(\)/);
  assert.match(source, /onClick=\{closeMobileRail\}/);
});
