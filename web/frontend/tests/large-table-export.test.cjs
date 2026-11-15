const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');
const JSZip = require('jszip');

function exporter() {
  const downloads = [];
  const tables = {};
  const api = {};
  const refs = {};
  const compile = name => ts.transpileModule(
    fs.readFileSync(path.join(__dirname, '../src/lib', name), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      esModuleInterop: true } },
  ).outputText;
  vm.runInNewContext(compile('coverageTables.ts'), { exports: tables, require });
  vm.runInNewContext(compile('socmRefs.ts'), { exports: refs, require });
  vm.runInNewContext(compile('resultExport.ts'), {
    exports: api, require: name => name === '@/lib/coverageTables' ? tables : name === '@/lib/socmRefs' ? refs : require(name),
    Blob, URL: { createObjectURL(blob) { downloads.push(blob); return 'blob:test'; }, revokeObjectURL() {} },
    document: { createElement: () => ({ style: {}, click() {}, remove() {} }), body: { appendChild() {} } },
    setTimeout() {},
  });
  return { api, downloads };
}

test('万行 CSV 与研究包保留完整记录、长值和未完成状态', async () => {
  const { api, downloads } = exporter();
  const entities = Array.from({ length: 10000 }, (_, i) => JSON.stringify([`Entity${i}`]));
  const longValue = '完整值 '.repeat(100);
  const cells = Object.fromEntries(entities.map((e, i) => [JSON.stringify(['t', JSON.parse(e), 'Value']), {
    status: i % 3 === 0 ? 'filled' : i % 3 === 1 ? 'missing' : 'hard_cell',
    value: i % 3 === 0 ? longValue : '', display_hint: 'preview',
    supporting_evidence_ids: i % 3 === 0 ? ['source'] : [],
  }]));
  const turn = { query: '大表', answer: '已保存部分结果。', status: 'completed', meta: {},
    events: [], workers: [], searchState: { coverage_map: {
      tables: { t: { table_id: 't', entities, primary_key: ['Name'], attributes: ['Name', 'Value'] } },
      cells, relations: [],
    }, evidence_graph: { nodes: [{ id: 'source', source: 'https://example.org/data' }], edges: [] } },
  };
  const before = JSON.stringify(turn.searchState);
  await api.exportTurnResults(turn, 'csv');
  const csv = await downloads[0].text();
  assert.equal(csv.trimEnd().split('\r\n').length, 10001);
  assert.ok(csv.includes(`"Entity9999","${longValue}"`));
  assert.ok(csv.includes('"Entity1",""'));
  assert.ok(csv.includes('"Entity2","N/A"'));
  await api.exportTurnResults(turn, 'package');
  const zip = await JSZip.loadAsync(Buffer.from(await downloads[1].arrayBuffer()));
  const coverage = JSON.parse(await zip.file('coverage.json').async('string'));
  assert.equal(coverage.tables.t.entities.length, 10000);
  assert.equal(coverage.cells[JSON.stringify(['t', ['Entity9999'], 'Value'])].value, longValue);
  assert.equal(coverage.cells[JSON.stringify(['t', ['Entity2'], 'Value'])].status, 'hard_cell');
  const csvPath = Object.keys(zip.files).find(name => name.endsWith('.csv'));
  assert.equal((await zip.file(csvPath).async('string')).trimEnd().split('\r\n').length, 10001);
  assert.ok((await zip.file('evidence.json').async('string')).includes('https://example.org/data'));
  assert.equal(JSON.stringify(turn.searchState), before);
});

test('导出读取主键单元格原值，保留字段内的分隔符', () => {
  const { api } = exporter();
  const entity = JSON.stringify(['Acme|EU', 'Blue|Label']);
  const tables = api.buildExportTables({
    tables: { t: { table_id: 't', entities: [entity],
      primary_key: ['Brand', 'Product'], attributes: ['Brand', 'Product', 'Size'] } },
    cells: {
      [JSON.stringify(['t', JSON.parse(entity), 'Brand'])]: { status: 'filled', value: 'Acme|EU' },
      [JSON.stringify(['t', JSON.parse(entity), 'Product'])]: { status: 'filled', value: 'Blue|Label' },
      [JSON.stringify(['t', JSON.parse(entity), 'Size'])]: { status: 'missing', value: '' },
    },
    relations: [],
  });
  assert.equal(tables[0].rows[0].Brand, 'Acme|EU');
  assert.equal(tables[0].rows[0].Product, 'Blue|Label');
  assert.equal(tables[0].rows[0].Size, '');
});
