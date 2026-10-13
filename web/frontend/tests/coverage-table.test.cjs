/* eslint-disable @typescript-eslint/no-require-imports -- Node test loads the TSX component directly. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function loadCoverageTable() {
  const helperSource = fs.readFileSync(
    path.join(__dirname, "../src/lib/coverageTables.ts"),
    "utf8",
  );
  const helperExports = {};
  vm.runInNewContext(ts.transpileModule(helperSource, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText, { exports: helperExports, require });
  const source = fs.readFileSync(
    path.join(__dirname, "../src/components/coverage/CoverageTable.tsx"),
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
    document: { body: {} },
    require(name) {
      if (name === "react-dom") return { createPortal: (element) => element };
      if (name === "./CellEvidencePopover") return { __esModule: true, default: () => null };
      if (name === "@/lib/coverageTables") return helperExports;
      return require(name);
    },
  });
  return exports.default;
}

test("coverage renders every declared schema even when another table has cells", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const CoverageTable = loadCoverageTable();
  const coverageMap = {
    tables: {
      filled: {
        table_id: "filled", table_label: "Filled table", entities: ["A"],
        attributes: ["Name", "Value"], primary_key: ["Name"], row_label: "Name",
      },
      empty: {
        table_id: "empty", table_label: "Empty schema", entities: [],
        attributes: ["Name", "Guidance"], primary_key: ["Name"], row_label: "Name",
      },
    },
    cells: {
      "filled/A.Value": { status: "filled", value: "Ready", supporting_evidence_ids: [] },
    },
    relations: [],
  };

  const html = renderToStaticMarkup(React.createElement(CoverageTable, { coverageMap }));

  assert.match(html, /Filled table/);
  assert.match(html, /Empty schema/);
  assert.match(html, /No rows yet/);
});

test("coverage does not expose an internal placeholder as a declared schema", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const CoverageTable = loadCoverageTable();
  const coverageMap = {
    tables: {
      _default: {
        table_id: "_default", table_label: "Internal placeholder", entities: ["query"],
        attributes: ["value"],
      },
    },
    cells: {},
    relations: [],
  };

  const html = renderToStaticMarkup(React.createElement(CoverageTable, { coverageMap }));

  assert.match(html, /No coverage data yet/);
  assert.doesNotMatch(html, /Internal placeholder/);
});
