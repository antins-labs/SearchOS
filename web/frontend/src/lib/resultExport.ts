import type { Turn } from "@/lib/conversation";
import type { CoverageCell, CoverageMap, Relation, TableSchema } from "@/lib/types";

type ExportValue = string | string[];

export interface ExportTable {
  id: string;
  label: string;
  columns: string[];
  rows: Record<string, ExportValue>[];
  schema: TableSchema;
}

export type ResultExportFormat = "csv" | "xlsx" | "json" | "package";

function safeName(value: string, fallback: string): string {
  const cleaned = value
    .trim()
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 72)
    .replace(/^-+|-+$/g, "");
  return cleaned || fallback;
}

function cellValue(cell: CoverageCell | undefined): ExportValue {
  if (!cell || cell.status === "missing") return "";
  if (cell.status === "hard_cell" && (!cell.value || cell.value.length === 0)) return "N/A";
  return cell.value;
}

function primaryKeyValues(schema: TableSchema, entity: string): string[] {
  const keys = schema.primary_key ?? [];
  if (keys.length <= 1) return [entity];
  const parts = entity.split("|");
  return keys.map((_, index) => parts[index] ?? (index === 0 ? entity : ""));
}

export function buildExportTables(coverageMap: CoverageMap): ExportTable[] {
  const allTables = Object.values(coverageMap.tables ?? {});
  const nonPlaceholder = allTables.filter((table) => !table.table_id.startsWith("_"));
  const base = nonPlaceholder.length ? nonPlaceholder : allTables;
  const withCells = base.filter((table) => Object.keys(coverageMap.cells).some((key) => key.startsWith(`${table.table_id}/`)));
  const tables = withCells.length ? withCells : base;

  return tables.map((schema) => {
    const primaryKeys = schema.primary_key?.length
      ? schema.primary_key
      : [schema.row_label || "Entity"];
    const dataColumns = schema.attributes.filter((attribute) => !(schema.primary_key ?? []).includes(attribute));
    const columns = [...primaryKeys, ...dataColumns];
    const rows = schema.entities.map((entity) => {
      const row: Record<string, ExportValue> = {};
      const keyValues = primaryKeyValues(schema, entity);
      primaryKeys.forEach((key, index) => { row[key] = keyValues[index] ?? ""; });
      dataColumns.forEach((attribute) => {
        row[attribute] = cellValue(coverageMap.cells[`${schema.table_id}/${entity}.${attribute}`]);
      });
      return row;
    });
    return {
      id: schema.table_id,
      label: schema.table_label || (schema.table_id.startsWith("_") ? "Results" : schema.table_id),
      columns,
      rows,
      schema,
    };
  });
}

function csvValue(value: ExportValue): string {
  let text = Array.isArray(value) ? value.join(" | ") : String(value ?? "");
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function tableToCsv(table: ExportTable): string {
  const lines = [
    table.columns.map((column) => csvValue(column)).join(","),
    ...table.rows.map((row) => table.columns.map((column) => csvValue(row[column] ?? "")).join(",")),
  ];
  return `\uFEFF${lines.join("\r\n")}\r\n`;
}

function relationRows(relations: Relation[]): Record<string, string>[] {
  return relations.map((relation) => ({
    from_table: relation.from_table,
    foreign_key: relation.foreign_key.columns.join(", "),
    to_table: relation.foreign_key.target_table,
    target_columns: relation.foreign_key.target_columns.join(", "),
    kind: relation.kind,
    label: relation.label ?? "",
  }));
}

function relationsCsv(relations: Relation[]): string {
  const columns = ["from_table", "foreign_key", "to_table", "target_columns", "kind", "label"];
  const rows = relationRows(relations);
  return `\uFEFF${[
    columns.map(csvValue).join(","),
    ...rows.map((row) => columns.map((column) => csvValue(row[column] ?? "")).join(",")),
  ].join("\r\n")}\r\n`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  globalThis.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportMetadata(turn: Turn) {
  return {
    version: 1,
    exported_at: new Date().toISOString(),
    session_id: turn.sessionId,
    query: turn.query,
    status: turn.status,
    state_source: turn.stateSource ?? "live",
    coverage_score: turn.meta.coverageScore ?? null,
    evidence_count: turn.meta.evidenceCount ?? turn.searchState?.evidence_graph.nodes.length ?? 0,
    elapsed_s: turn.meta.elapsed ?? null,
    verdict: turn.meta.verdict ?? null,
    event_count: turn.events.length,
    agent_count: turn.workers.length,
  };
}

function jsonPayload(turn: Turn, tables: ExportTable[]) {
  const coverageMap = turn.searchState!.coverage_map;
  return {
    ...exportMetadata(turn),
    tables: tables.map((table) => ({
      table_id: table.id,
      table_label: table.label,
      schema: table.schema,
      primary_key: table.schema.primary_key ?? [],
      row_label: table.schema.row_label ?? "",
      columns: table.columns,
      rows: table.rows,
    })),
    relations: relationRows(coverageMap.relations ?? []),
  };
}

function sheetName(name: string, used: Set<string>): string {
  const base = name.replace(/[\\/?*\[\]:]/g, "-").slice(0, 31) || "Table";
  let candidate = base;
  let suffix = 2;
  while (used.has(candidate)) {
    const marker = `-${suffix++}`;
    candidate = `${base.slice(0, 31 - marker.length)}${marker}`;
  }
  used.add(candidate);
  return candidate;
}

async function exportCsv(turn: Turn, tables: ExportTable[], stem: string) {
  const relations = turn.searchState!.coverage_map.relations ?? [];
  if (tables.length === 1) {
    downloadBlob(new Blob([tableToCsv(tables[0])], { type: "text/csv;charset=utf-8" }), `${stem}.csv`);
    return;
  }

  const { default: JSZip } = await import("jszip");
  const zip = new JSZip();
  const folder = zip.folder("tables")!;
  tables.forEach((table, index) => {
    folder.file(`${String(index + 1).padStart(2, "0")}-${safeName(table.label, table.id)}.csv`, tableToCsv(table));
  });
  if (relations.length) zip.file("relations.csv", relationsCsv(relations));
  const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
  downloadBlob(blob, `${stem}-csv.zip`);
}

async function exportXlsx(turn: Turn, tables: ExportTable[], stem: string) {
  const ExcelJS = (await import("exceljs")).default;
  const workbook = new ExcelJS.Workbook();
  workbook.creator = "SearchOS";
  workbook.created = new Date();
  const usedNames = new Set<string>();

  tables.forEach((table) => {
    const sheet = workbook.addWorksheet(sheetName(table.label, usedNames));
    sheet.addRow(table.columns);
    table.rows.forEach((row) => sheet.addRow(table.columns.map((column) => {
      const value = row[column] ?? "";
      return Array.isArray(value) ? value.join("\n") : value;
    })));
    sheet.views = [{ state: "frozen", ySplit: 1 }];
    sheet.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: Math.max(table.columns.length, 1) } };
    sheet.getRow(1).font = { bold: true, color: { argb: "FFFFFFFF" } };
    sheet.getRow(1).fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF5C655D" } };
    sheet.getRow(1).alignment = { vertical: "middle" };
    sheet.columns.forEach((column, index) => {
      const longest = Math.max(table.columns[index]?.length ?? 0, ...table.rows.slice(0, 200).map((row) => {
        const value = row[table.columns[index]] ?? "";
        return (Array.isArray(value) ? value.join(" ") : String(value)).length;
      }));
      column.width = Math.min(Math.max(longest + 2, 12), 42);
      column.alignment = { vertical: "top", wrapText: true };
    });
  });

  const relations = turn.searchState!.coverage_map.relations ?? [];
  if (relations.length) {
    const sheet = workbook.addWorksheet(sheetName("Relations", usedNames));
    const columns = ["from_table", "foreign_key", "to_table", "target_columns", "kind", "label"];
    sheet.addRow(columns);
    relationRows(relations).forEach((row) => sheet.addRow(columns.map((column) => row[column])));
    sheet.getRow(1).font = { bold: true };
    sheet.views = [{ state: "frozen", ySplit: 1 }];
  }

  const metadataSheet = workbook.addWorksheet(sheetName("Metadata", usedNames));
  Object.entries(exportMetadata(turn)).forEach(([key, value]) => metadataSheet.addRow([key, value ?? ""]));
  metadataSheet.getColumn(1).width = 24;
  metadataSheet.getColumn(2).width = 64;

  const output = await workbook.xlsx.writeBuffer();
  const bytes = new Uint8Array(output.byteLength);
  bytes.set(new Uint8Array(output));
  downloadBlob(
    new Blob([bytes.buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
    `${stem}.xlsx`,
  );
}

async function exportResearchPackage(turn: Turn, tables: ExportTable[], stem: string) {
  const { default: JSZip } = await import("jszip");
  const zip = new JSZip();
  const state = turn.searchState!;
  const metadata = exportMetadata(turn);
  const sources = new Map<string, { source: string; evidence_ids: string[] }>();
  state.evidence_graph.nodes.forEach((node) => {
    if (!node.source) return;
    const item = sources.get(node.source) ?? { source: node.source, evidence_ids: [] };
    item.evidence_ids.push(node.id);
    sources.set(node.source, item);
  });

  zip.file("manifest.json", JSON.stringify({
    version: 1,
    format: "searchos-research-package",
    files: {
      "answer.md": "Rendered answer in Markdown",
      "metadata.json": "Run and export metadata",
      "coverage.json": "Raw CoverageMap including schemas, cells and relations",
      "evidence.json": "Evidence graph nodes and edges",
      "relations.json": "Table relationship definitions",
      "sources.json": "Unique sources mapped to evidence ids",
      "tables.json": "Normalized multi-table result data",
      "tables/*.csv": "One UTF-8 CSV per result table",
    },
  }, null, 2));
  zip.file("answer.md", `# ${turn.query}\n\n${turn.answer.trim()}\n`);
  zip.file("metadata.json", JSON.stringify(metadata, null, 2));
  zip.file("coverage.json", JSON.stringify(state.coverage_map, null, 2));
  zip.file("evidence.json", JSON.stringify(state.evidence_graph, null, 2));
  zip.file("relations.json", JSON.stringify(state.coverage_map.relations ?? [], null, 2));
  zip.file("sources.json", JSON.stringify([...sources.values()], null, 2));
  zip.file("tables.json", JSON.stringify(jsonPayload(turn, tables), null, 2));
  const folder = zip.folder("tables")!;
  tables.forEach((table, index) => {
    folder.file(`${String(index + 1).padStart(2, "0")}-${safeName(table.label, table.id)}.csv`, tableToCsv(table));
  });
  const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
  downloadBlob(blob, `${stem}-research-package.zip`);
}

export async function exportTurnResults(turn: Turn, format: ResultExportFormat): Promise<string> {
  if (!turn.searchState?.coverage_map || Object.keys(turn.searchState.coverage_map.tables ?? {}).length === 0) {
    throw new Error("No result tables are available for this turn");
  }
  const tables = buildExportTables(turn.searchState.coverage_map);
  if (!tables.length) throw new Error("No exportable tables are available for this turn");
  const stem = safeName(turn.query, "searchos-results");

  if (format === "csv") await exportCsv(turn, tables, stem);
  if (format === "xlsx") await exportXlsx(turn, tables, stem);
  if (format === "json") {
    downloadBlob(
      new Blob([JSON.stringify(jsonPayload(turn, tables), null, 2)], { type: "application/json;charset=utf-8" }),
      `${stem}.json`,
    );
  }
  if (format === "package") await exportResearchPackage(turn, tables, stem);
  return format === "package" ? "Research package download started" : `${format.toUpperCase()} download started`;
}
