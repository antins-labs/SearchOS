"use client";

import { useState } from "react";
import type { CoverageMap, TableSchema, CoverageCell, EvidenceNode } from "@/lib/types";
import CellEvidencePopover, { type CellRef } from "./CellEvidencePopover";

interface Props {
  coverageMap: CoverageMap | null;
  /** When provided, filled cells become clickable and open their evidence. */
  evidence?: EvidenceNode[];
}

// Filled cells stay readable (near-normal text) with only a whisper of tint —
// the value matters more than a loud highlight. A small left dot signals "filled".
const STATUS_COLORS: Record<string, string> = {
  filled: "text-ink",
  missing: "text-ink-faint",
  uncertain: "text-accent-ink dark:text-amber-300/80",
  hard_cell: "text-err dark:text-err",
};

function renderCellValue(cell: CoverageCell): React.ReactNode {
  if (cell.status === "filled") {
    const dot = <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ok/70" />;
    if (Array.isArray(cell.value)) {
      return (
        <div className="flex items-start gap-1.5">
          {dot}
          <div className="space-y-0.5">
            {cell.value.map((v, vi) => (
              <div key={vi} className="text-xs">{vi + 1}. {v}</div>
            ))}
          </div>
        </div>
      );
    }
    return (
      <span className="flex items-start gap-1.5">
        {dot}
        <span>{cell.value}</span>
      </span>
    );
  }
  if (cell.status === "hard_cell") return <span className="text-err">N/A</span>;
  return <span className="text-ink-faint">…</span>;
}

function TableSection({
  schema,
  cells,
  onCellClick,
}: {
  schema: TableSchema;
  cells: Record<string, CoverageCell>;
  onCellClick?: (ref: CellRef) => void;
}) {
  const { table_id, entities, attributes, primary_key, row_label, table_label } = schema;
  // A single auto-created table is named "_default" by the backend — show a
  // friendly name and hide the raw id badge for it.
  const isDefault = table_id === "_default" || table_id.startsWith("_");
  const displayName = table_label || (isDefault ? "Results" : table_id);
  const showId = !isDefault && table_id !== displayName;
  const hasKeys = primary_key && primary_key.length > 0;
  const rowHeader = hasKeys ? (row_label || primary_key!.join(" / ")) : (row_label || "Entity");
  const dataCols = hasKeys ? attributes.filter((a) => !primary_key!.includes(a)) : attributes;

  const prefix = `${table_id}/`;
  const tableCells = Object.entries(cells).filter(([k]) => k.startsWith(prefix));
  const filled = tableCells.filter(([, c]) => c.status === "filled").length;
  const total = tableCells.length;
  const pct = total > 0 ? (filled / total) * 100 : 0;

  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-ink">
          {displayName}
          {showId && (
            <span className="ml-1.5 text-xs text-ink-faint">[{table_id}]</span>
          )}
        </h3>
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-24 rounded-full bg-surface-2">
            <div
              className="h-1.5 rounded-full bg-accent/70 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs text-ink-dim">{filled}/{total} ({pct.toFixed(0)}%)</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line">
              <th className="px-3 py-2 text-left text-xs font-medium text-ink-dim whitespace-nowrap">{rowHeader}</th>
              {dataCols.map((attr) => (
                <th key={attr} className="px-3 py-2 text-left text-xs font-medium text-ink-dim whitespace-nowrap min-w-[140px]">
                  {attr}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entities.map((entity) => {
              const entityDisplay = hasKeys ? entity.replace(/\|/g, " / ") : entity;
              return (
                <tr key={entity} className="border-b border-line">
                  <td className="px-3 py-2 font-medium text-ink whitespace-nowrap">{entityDisplay}</td>
                  {dataCols.map((attr) => {
                    const cell = cells[`${table_id}/${entity}.${attr}`];
                    if (!cell) return <td key={attr} className="px-3 py-2 text-ink-faint">--</td>;
                    const sourceTitle = Array.isArray(cell.source) ? cell.source.join(", ") : cell.source;
                    const clickable = !!onCellClick && cell.status !== "missing";
                    const cellTitle = cell.status === "filled"
                      ? (typeof cell.value === "string" ? cell.value : Array.isArray(cell.value) ? cell.value.join("\n") : "")
                      : sourceTitle ? `Source: ${sourceTitle}` : undefined;
                    return (
                      <td
                        key={attr}
                        className={`px-3 py-2 whitespace-nowrap ${STATUS_COLORS[cell.status] || ""} ${
                          clickable ? "cursor-pointer transition-colors hover:bg-clay/40" : ""
                        }`}
                        title={clickable ? `${cellTitle ?? ""}${cellTitle ? "\n" : ""}Click to view evidence` : cellTitle}
                        onClick={clickable ? () => onCellClick({ tableId: table_id, entity, attribute: attr, cell }) : undefined}
                      >
                        {renderCellValue(cell)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {entities.length === 0 && (
              <tr>
                <td className="px-3 py-2 text-xs italic text-ink-faint" colSpan={dataCols.length + 1}>
                  no rows yet (column-only schema — rows will be discovered during search)
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function CoverageTable({ coverageMap, evidence }: Props) {
  const [selected, setSelected] = useState<CellRef | null>(null);

  if (!coverageMap || !coverageMap.tables || Object.keys(coverageMap.tables).length === 0) {
    return <div className="p-4 text-sm text-ink-faint">No coverage data yet.</div>;
  }

  const allTables = Object.values(coverageMap.tables);
  const cellKeys = Object.keys(coverageMap.cells);
  // Drop the "_default" placeholder table (single meta-entity = the query
  // subject, never filled) once a real table exists. Then drop tables with no
  // cells. Fall back so we never render nothing.
  const nonPlaceholder = allTables.filter((t) => !t.table_id.startsWith("_"));
  const base = nonPlaceholder.length ? nonPlaceholder : allTables;
  const withCells = base.filter((t) => cellKeys.some((k) => k.startsWith(`${t.table_id}/`)));
  const tables = withCells.length ? withCells : base;
  const relations = coverageMap.relations || [];

  return (
    <div className="p-4">
      {tables.map((schema) => (
        <TableSection
          key={schema.table_id}
          schema={schema}
          cells={coverageMap.cells}
          onCellClick={evidence ? setSelected : undefined}
        />
      ))}

      {selected && evidence && (
        <CellEvidencePopover cellRef={selected} nodes={evidence} onClose={() => setSelected(null)} />
      )}

      {relations.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <h3 className="mb-2 text-sm font-medium text-ink">Relations</h3>
          <ul className="space-y-1 text-xs text-ink-dim">
            {relations.map((r, i) => (
              <li key={i}>
                <code className="text-ink">
                  {r.from_table}.[{r.foreign_key.columns.join(",")}]
                </code>
                {" → "}
                <code className="text-ink">
                  {r.foreign_key.target_table}.[{r.foreign_key.target_columns.join(",")}]
                </code>
                <span className="ml-2 text-ink-faint">({r.kind})</span>
                {r.label && <span className="ml-2 italic">— {r.label}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
