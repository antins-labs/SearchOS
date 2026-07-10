"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  Columns3,
  Filter,
  Maximize2,
  Minimize2,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
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

type SortState = { column: string; direction: "asc" | "desc" } | null;

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function cellText(cell: CoverageCell | undefined): string {
  if (!cell || cell.status === "missing") return "";
  if (cell.status === "hard_cell" && (!cell.value || cell.value.length === 0)) return "N/A";
  return Array.isArray(cell.value) ? cell.value.join(" ") : String(cell.value ?? "");
}

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
  evidenceOpen,
}: {
  schema: TableSchema;
  cells: Record<string, CoverageCell>;
  onCellClick?: (ref: CellRef) => void;
  evidenceOpen: boolean;
}) {
  const { table_id, entities, attributes, primary_key, row_label, table_label } = schema;
  const isDefault = table_id === "_default" || table_id.startsWith("_");
  const displayName = table_label || (isDefault ? "Results" : table_id);
  const showId = !isDefault && table_id !== displayName;
  const hasKeys = !!primary_key?.length;
  const rowHeader = hasKeys ? (row_label || primary_key!.join(" / ")) : (row_label || "Entity");
  const dataCols = useMemo(
    () => hasKeys ? attributes.filter((attribute) => !(primary_key ?? []).includes(attribute)) : attributes,
    [attributes, hasKeys, primary_key],
  );
  const filterableColumns = useMemo(() => [rowHeader, ...dataCols], [dataCols, rowHeader]);

  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(() => new Set());
  const [sort, setSort] = useState<SortState>(null);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [columnsMenuOpen, setColumnsMenuOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const toolbarRef = useRef<HTMLDivElement>(null);

  const visibleDataCols = useMemo(
    () => dataCols.filter((column) => !hiddenColumns.has(column)),
    [dataCols, hiddenColumns],
  );
  const activeFilters = Object.values(filters).filter((value) => value.trim()).length;
  const customized = !!query || activeFilters > 0 || hiddenColumns.size > 0 || !!sort;

  useEffect(() => {
    if (!filterMenuOpen && !columnsMenuOpen && !fullscreen) return;
    const onPointerDown = (event: PointerEvent) => {
      if ((filterMenuOpen || columnsMenuOpen) && !toolbarRef.current?.contains(event.target as Node)) {
        setFilterMenuOpen(false);
        setColumnsMenuOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (filterMenuOpen || columnsMenuOpen) {
        setFilterMenuOpen(false);
        setColumnsMenuOpen(false);
      } else if (fullscreen && !evidenceOpen) {
        setFullscreen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [columnsMenuOpen, evidenceOpen, filterMenuOpen, fullscreen]);

  useEffect(() => {
    if (!fullscreen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [fullscreen]);

  const displayEntity = useCallback(
    (entity: string) => hasKeys ? entity.replace(/\|/g, " / ") : entity,
    [hasKeys],
  );
  const valueFor = useCallback((entity: string, column: string) => column === rowHeader
    ? displayEntity(entity)
    : cellText(cells[`${table_id}/${entity}.${column}`]),
  [cells, displayEntity, rowHeader, table_id]);

  const visibleEntities = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const activeColumnFilters = Object.entries(filters)
      .map(([column, value]) => [column, value.trim().toLowerCase()] as const)
      .filter(([, value]) => value);

    const filtered = entities.filter((entity) => {
      if (normalizedQuery) {
        const rowText = [displayEntity(entity), ...dataCols.map((column) => valueFor(entity, column))]
          .join(" ")
          .toLowerCase();
        if (!rowText.includes(normalizedQuery)) return false;
      }
      return activeColumnFilters.every(([column, filter]) => valueFor(entity, column).toLowerCase().includes(filter));
    });

    if (!sort) return filtered;
    return [...filtered].sort((left, right) => {
      const a = valueFor(left, sort.column).trim();
      const b = valueFor(right, sort.column).trim();
      if (!a && !b) return 0;
      if (!a) return 1;
      if (!b) return -1;
      const result = collator.compare(a, b);
      return sort.direction === "asc" ? result : -result;
    });
  }, [dataCols, displayEntity, entities, filters, query, sort, valueFor]);

  const toggleSort = (column: string) => {
    setSort((current) => {
      if (!current || current.column !== column) return { column, direction: "asc" };
      if (current.direction === "asc") return { column, direction: "desc" };
      return null;
    });
  };

  const toggleColumn = (column: string) => {
    setHiddenColumns((current) => {
      const next = new Set(current);
      if (next.has(column)) next.delete(column);
      else next.add(column);
      return next;
    });
  };

  const resetView = () => {
    setQuery("");
    setFilters({});
    setHiddenColumns(new Set());
    setSort(null);
  };

  const prefix = `${table_id}/`;
  const tableCells = Object.entries(cells).filter(([k]) => k.startsWith(prefix));
  const filled = tableCells.filter(([, c]) => c.status === "filled").length;
  const total = tableCells.length;
  const pct = total > 0 ? (filled / total) * 100 : 0;

  const renderWorkbench = (isFullscreen: boolean) => (
    <section className={isFullscreen ? "surface flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-line" : "mb-6"}>
      <div className={`flex flex-wrap items-center gap-2 ${isFullscreen ? "border-b border-line px-3 py-3 sm:px-4" : "mb-2"}`}>
        <h3 className="min-w-0 text-sm font-medium text-ink">
          {displayName}
          {showId && <span className="ml-1.5 text-xs text-ink-faint">[{table_id}]</span>}
        </h3>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <div className="hidden h-1.5 w-20 rounded-full bg-surface-2 sm:block">
            <div className="h-1.5 rounded-full bg-accent/70 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-xs text-ink-dim">{filled}/{total} ({pct.toFixed(0)}%)</span>
          {isFullscreen && (
            <button type="button" onClick={() => setFullscreen(false)} title="Restore" aria-label="Restore table"
              className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
              <Minimize2 size={16} />
            </button>
          )}
        </div>
      </div>

      <div ref={toolbarRef} className={`flex flex-wrap items-center gap-1.5 border-y border-line bg-paper/60 p-2 ${isFullscreen ? "shrink-0" : ""}`}>
        <label className="flex h-8 min-w-[180px] flex-1 items-center gap-2 rounded-md border border-line bg-surface px-2.5 text-[12.5px] text-ink-faint focus-within:border-line-strong sm:max-w-[300px]">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search rows"
            className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint" />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Clear row search" title="Clear search"
              className="rounded p-0.5 hover:bg-surface-2 hover:text-ink"><X size={12} /></button>
          )}
        </label>

        <div className="relative">
          <button type="button" onClick={() => { setFilterMenuOpen((value) => !value); setColumnsMenuOpen(false); }}
            aria-label="Column filters" aria-haspopup="menu" aria-expanded={filterMenuOpen} title="Column filters"
            className={`flex h-8 items-center gap-1.5 rounded-md px-2 text-[12px] transition-colors hover:bg-surface-2 hover:text-ink ${filterMenuOpen || activeFilters ? "bg-clay text-accent-ink" : "text-ink-faint"}`}>
            <Filter size={14} />
            <span className="hidden sm:inline">Filters</span>
            {activeFilters > 0 && <span className="min-w-4 text-center text-[10px] font-semibold">{activeFilters}</span>}
          </button>
          {filterMenuOpen && (
            <div role="menu" aria-label="Column filters" className="surface absolute left-0 top-full z-40 mt-1 w-[min(300px,80vw)] rounded-lg p-2 shadow-xl">
              <div className="mb-2 flex items-center justify-between px-1 text-[11px] font-medium text-ink-dim">
                <span>Column filters</span>
                {activeFilters > 0 && (
                  <button type="button" onClick={() => setFilters({})} className="rounded px-1.5 py-0.5 text-ink-faint hover:bg-surface-2 hover:text-ink">Clear</button>
                )}
              </div>
              <div className="max-h-[300px] space-y-1.5 overflow-y-auto">
                {filterableColumns.map((column) => (
                  <label key={column} className="block">
                    <span className="mb-1 block truncate px-1 text-[10.5px] text-ink-faint" title={column}>{column}</span>
                    <span className="flex h-8 items-center rounded-md border border-line bg-paper px-2 focus-within:border-line-strong">
                      <input value={filters[column] ?? ""}
                        onChange={(event) => setFilters((current) => ({ ...current, [column]: event.target.value }))}
                        placeholder={`Filter ${column}`} className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-ink-faint" />
                      {filters[column] && (
                        <button type="button" onClick={() => setFilters((current) => ({ ...current, [column]: "" }))}
                          aria-label={`Clear ${column} filter`} className="rounded p-0.5 text-ink-faint hover:text-ink"><X size={11} /></button>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="relative">
          <button type="button" onClick={() => { setColumnsMenuOpen((value) => !value); setFilterMenuOpen(false); }}
            aria-label="Visible columns" aria-haspopup="menu" aria-expanded={columnsMenuOpen} title="Visible columns"
            className={`flex h-8 items-center gap-1.5 rounded-md px-2 text-[12px] transition-colors hover:bg-surface-2 hover:text-ink ${columnsMenuOpen || hiddenColumns.size ? "bg-clay text-accent-ink" : "text-ink-faint"}`}>
            <Columns3 size={14} />
            <span className="hidden sm:inline">Columns</span>
            {hiddenColumns.size > 0 && <span className="text-[10px]">-{hiddenColumns.size}</span>}
          </button>
          {columnsMenuOpen && (
            <div role="menu" aria-label="Visible columns" className="surface absolute right-0 top-full z-40 mt-1 w-[min(260px,78vw)] rounded-lg p-2 shadow-xl">
              <div className="mb-1.5 flex items-center justify-between px-1 text-[11px] font-medium text-ink-dim">
                <span>Visible columns</span>
                {hiddenColumns.size > 0 && (
                  <button type="button" onClick={() => setHiddenColumns(new Set())} className="rounded px-1.5 py-0.5 text-ink-faint hover:bg-surface-2 hover:text-ink">Show all</button>
                )}
              </div>
              <div className="max-h-[300px] overflow-y-auto">
                {dataCols.map((column) => (
                  <label key={column} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2 hover:text-ink">
                    <input type="checkbox" checked={!hiddenColumns.has(column)} onChange={() => toggleColumn(column)} className="h-3.5 w-3.5 accent-[var(--accent)]" />
                    <span className="min-w-0 flex-1 truncate" title={column}>{column}</span>
                    {!hiddenColumns.has(column) && <Check size={12} className="text-accent-ink" />}
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {customized && (
          <button type="button" onClick={resetView} aria-label="Reset table view" title="Reset table view"
            className="grid h-8 w-8 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
            <RotateCcw size={14} />
          </button>
        )}
        {!isFullscreen && (
          <button type="button" onClick={() => setFullscreen(true)} aria-label="Open table fullscreen" title="Open fullscreen"
            className="grid h-8 w-8 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
            <Maximize2 size={14} />
          </button>
        )}
        <span className="ml-auto whitespace-nowrap px-1 text-[11px] text-ink-faint">{visibleEntities.length}/{entities.length} rows</span>
      </div>

      <div className={`${isFullscreen ? "min-h-0 flex-1" : "max-h-[440px]"} overflow-auto border-b border-line`}>
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th aria-sort={sort?.column === rowHeader ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                className="sticky left-0 top-0 z-30 min-w-[180px] border-b border-r border-line bg-surface-2 px-3 py-2 text-left text-xs font-medium text-ink-dim">
                <button type="button" onClick={() => toggleSort(rowHeader)} title={`Sort by ${rowHeader}`}
                  className="flex w-full items-center gap-1.5 whitespace-nowrap text-left hover:text-ink">
                  <span className="truncate">{rowHeader}</span>
                  <SortIndicator column={rowHeader} sort={sort} />
                </button>
              </th>
              {visibleDataCols.map((column) => (
                <th key={column} aria-sort={sort?.column === column ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  className="sticky top-0 z-20 min-w-[140px] border-b border-line bg-surface-2 px-3 py-2 text-left text-xs font-medium text-ink-dim">
                  <button type="button" onClick={() => toggleSort(column)} title={`Sort by ${column}`}
                    className="flex w-full items-center gap-1.5 whitespace-nowrap text-left hover:text-ink">
                    <span className="truncate">{column}</span>
                    <SortIndicator column={column} sort={sort} />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleEntities.map((entity) => (
              <tr key={entity} className="group">
                <td className="sticky left-0 z-10 whitespace-nowrap border-b border-r border-line bg-surface px-3 py-2 font-medium text-ink group-hover:bg-surface-2">
                  {displayEntity(entity)}
                </td>
                {visibleDataCols.map((column) => {
                  const cell = cells[`${table_id}/${entity}.${column}`];
                  if (!cell) return <td key={column} className="whitespace-nowrap border-b border-line px-3 py-2 text-ink-faint">--</td>;
                  const sourceTitle = Array.isArray(cell.source) ? cell.source.join(", ") : cell.source;
                  const clickable = !!onCellClick && cell.status !== "missing";
                  const cellTitle = cell.status === "filled"
                    ? (typeof cell.value === "string" ? cell.value : Array.isArray(cell.value) ? cell.value.join("\n") : "")
                    : sourceTitle ? `Source: ${sourceTitle}` : undefined;
                  return (
                    <td key={column}
                      className={`whitespace-nowrap border-b border-line px-3 py-2 ${STATUS_COLORS[cell.status] || ""} ${clickable ? "cursor-pointer transition-colors hover:bg-clay/40" : ""}`}
                      title={clickable ? `${cellTitle ?? ""}${cellTitle ? "\n" : ""}Click to view evidence` : cellTitle}
                      onClick={clickable ? () => onCellClick({ tableId: table_id, entity, attribute: column, cell }) : undefined}>
                      {renderCellValue(cell)}
                    </td>
                  );
                })}
              </tr>
            ))}
            {visibleEntities.length === 0 && (
              <tr>
                <td className="px-3 py-6 text-center text-xs italic text-ink-faint" colSpan={visibleDataCols.length + 1}>
                  {entities.length === 0 ? "No rows yet" : "No rows match the current search and filters"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );

  return (
    <>
      {!fullscreen && renderWorkbench(false)}
      {fullscreen && createPortal(
        <div className="fade-in fixed inset-0 z-[65] bg-paper p-2 sm:p-4">{renderWorkbench(true)}</div>,
        document.body,
      )}
    </>
  );
}

function SortIndicator({ column, sort }: { column: string; sort: SortState }) {
  if (sort?.column !== column) return <ArrowUpDown className="shrink-0 opacity-35" size={12} />;
  return sort.direction === "asc"
    ? <ArrowUp className="shrink-0 text-accent-ink" size={12} />
    : <ArrowDown className="shrink-0 text-accent-ink" size={12} />;
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
          evidenceOpen={!!selected}
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
