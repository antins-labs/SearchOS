/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');

// Execute the real hook's handlers with a report and its nested entry dialog.
function setup() {
  const listeners = [], modals = [];
  class Element {
    constructor(parent = null) { this.parent = parent; this.focused = false; }
    contains(other) { return other === this || !!other?.parent && this.contains(other.parent); }
    focus() { this.focused = true; doc.activeElement = this; }
    getAttribute() { return null; }
    querySelectorAll() { return this.controls || []; }
  }
  const doc = { activeElement: null, body: { style: { overflow: '' } }, querySelectorAll: () => modals,
    addEventListener: (_, handler) => listeners.push(handler), removeEventListener() {} };
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/hooks/useDialogFocus.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, { exports, HTMLElement: Element, document: doc,
    window: { requestAnimationFrame: callback => { callback(); return 1; }, cancelAnimationFrame() {} },
    require: () => ({ useRef: value => ({ current: value }), useEffect: callback => callback() }),
  });
  const open = (element, onClose) => { modals.push(element); exports.default({ containerRef: { current: element }, onClose }); };
  const key = (value, shiftKey = false) => { const event = { key: value, shiftKey, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {} }; listeners.forEach(handler => handler(event)); };
  return { Element, doc, open, key };
}

test('Escape closes an entry dialog without closing its parent report', () => {
  const { Element, open, key } = setup();
  const closed = [], report = new Element(), entry = new Element(report);
  open(report, () => closed.push('report')); open(entry, () => closed.push('entry'));
  key('Escape');
  assert.deepEqual(closed, ['entry']);
});

test('Tab stays in the active entry instead of jumping to the parent report', () => {
  const { Element, doc, open, key } = setup();
  const report = new Element(), entry = new Element(report);
  const reportButton = new Element(report), first = new Element(entry), last = new Element(entry);
  report.controls = [reportButton, first, last]; entry.controls = [first, last];
  open(report, () => {}); open(entry, () => {});
  last.focus(); key('Tab'); assert.equal(doc.activeElement, first);
  key('Tab', true); assert.equal(doc.activeElement, last);
  assert.equal(reportButton.focused, false);
});
