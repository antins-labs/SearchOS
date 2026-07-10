"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { ArrowUp, Gauge, KeyRound, Plus, SlidersHorizontal, Square, Table2, X } from "lucide-react";

import { useSettings } from "@/components/settings/SettingsProvider";
import RunOverridesPopover from "@/components/settings/RunOverridesPopover";
import Select from "@/components/ui/Select";

export interface SubmitOpts {
  type?: string;
  entities?: string[];
  attrs?: string[];
  tableLabel?: string;
  primaryKey?: string[];
  rowLabel?: string;
  tables?: {
    table_id: string;
    table_label?: string;
    entities?: string[];
    attrs: string[];
    primary_key?: string[];
    row_label?: string;
  }[];
  relations?: {
    from_table: string;
    to_table: string;
    foreign_key: string[];
    target_columns?: string[];
    kind: "one_to_many" | "many_to_many";
    label?: string;
  }[];
}

interface Props {
  onSubmit: (query: string, opts: SubmitOpts) => void;
  /** When set, submitting while `running` steers the live run instead of being ignored. */
  onSteer?: (text: string) => void;
  /** When set, a stop button interrupts the live run while `running`. */
  onStop?: () => void;
  running?: boolean;
  /** "hero" = large landing composer, "bar" = compact in-conversation bar */
  variant?: "hero" | "bar";
  placeholder?: string;
  autoFocus?: boolean;
}

const COMMANDS = [
  { cmd: "/wide", hint: "Compare entities across attributes — forge a table" },
  { cmd: "/deep", hint: "Hunt down one hard-to-find fact" },
  { cmd: "/local", hint: "Search the local corpus" },
  { cmd: "/schema", hint: "Pin rows (entities) and cols (attributes)" },
];

const csv = (s: string) => {
  const items = s.split(",").map((x) => x.trim()).filter(Boolean);
  return items.length ? items : undefined;
};

type TableDraft = {
  id: string;
  entityName: string;
  primaryKey: string;
  rows: string[];
  columns: string[];
};

type RelationDraft = {
  id: string;
  fromDraftId: string;
  fromColumn: string;
  toDraftId: string;
  kind: "one_to_many" | "many_to_many";
  label: string;
};

type DrawPoint = {
  x: number;
  y: number;
};

type DrawPreview = DrawPoint & {
  width: number;
  height: number;
  rows: number;
  cols: number;
};

const DRAW_CELL_W = 108;
const DRAW_CELL_H = 34;
const MIN_DRAW_SIZE = 26;

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));

const cleanList = (items: string[]) => {
  const cleaned = items.map((x) => x.trim()).filter(Boolean);
  return cleaned.length ? cleaned : undefined;
};

const makeDraft = (rows: number, dataCols: number, index: number): TableDraft => ({
  id: `draft_${Date.now()}_${index}`,
  entityName: "",
  primaryKey: "",
  rows: Array.from({ length: rows }, () => ""),
  columns: Array.from({ length: dataCols }, (_, i) => `字段 ${i + 1}`),
});

const tableSlug = (label: string, index: number) => {
  const slug = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `${slug || "table"}_${index + 1}`;
};

const draftLabel = (draft: TableDraft, index: number) => draft.entityName.trim() || `Table ${index + 1}`;

const draftPrimaryKey = (draft: TableDraft) => {
  const label = draft.entityName.trim();
  return draft.primaryKey.trim() || (label ? `${label} ID` : "ID");
};

const draftAttrs = (draft: TableDraft, index: number) => [
  draftPrimaryKey(draft),
  ...(cleanList(draft.columns) ?? [`字段 ${index + 1}`]),
];

export default function Composer({
  onSubmit,
  onSteer,
  onStop,
  running = false,
  variant = "bar",
  placeholder,
  autoFocus = false,
}: Props) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [showSchema, setShowSchema] = useState(false);
  const [showOverrides, setShowOverrides] = useState(false);
  const [entities, setEntities] = useState("");
  const [attrs, setAttrs] = useState("");
  const [tableDrafts, setTableDrafts] = useState<TableDraft[]>([]);
  const [relationDrafts, setRelationDrafts] = useState<RelationDraft[]>([]);
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const [dragStart, setDragStart] = useState<DrawPoint | null>(null);
  const [dragNow, setDragNow] = useState<DrawPoint | null>(null);
  const [sel, setSel] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const { overrides, clearOverrides } = useSettings();

  const overridesActive = overrides.effort != null || overrides.max_time != null;
  // Pinned schema follows the *content*, not the panel visibility — collapsing
  // the panel must not silently drop what the user typed.
  const activeDraft = tableDrafts.find((draft) => draft.id === activeDraftId) ?? null;
  const hasDraftTables = tableDrafts.length > 0;
  const resolvedEntityName = activeDraft?.entityName.trim() ?? "";
  const resolvedPrimaryKey = activeDraft?.primaryKey.trim() || (resolvedEntityName ? `${resolvedEntityName} ID` : "ID");
  const draftRows = activeDraft ? cleanList(activeDraft.rows) : undefined;
  const draftDataCols = activeDraft ? cleanList(activeDraft.columns) : undefined;
  const draftCols = activeDraft ? [resolvedPrimaryKey, ...(draftDataCols ?? [])] : undefined;
  const tableMetas = tableDrafts.map((draft, index) => {
    const label = draftLabel(draft, index);
    const primaryKey = draftPrimaryKey(draft);
    return {
      draft,
      tableId: tableSlug(label, index),
      label,
      primaryKey,
      attrs: draftAttrs(draft, index),
    };
  });
  const tableMetaByDraftId = new Map(tableMetas.map((meta) => [meta.draft.id, meta]));
  const schemaTables = hasDraftTables
    ? tableMetas.map((meta) => ({
      table_id: meta.tableId,
      table_label: meta.label,
      entities: cleanList(meta.draft.rows),
      attrs: meta.attrs,
      primary_key: [meta.primaryKey],
      row_label: meta.label,
    }))
    : undefined;
  const schemaRelations = hasDraftTables
    ? relationDrafts.flatMap((rel) => {
      const from = tableMetaByDraftId.get(rel.fromDraftId);
      const to = tableMetaByDraftId.get(rel.toDraftId);
      if (!from || !to || !rel.fromColumn.trim()) return [];
      return [{
        from_table: from.tableId,
        to_table: to.tableId,
        foreign_key: [rel.fromColumn.trim()],
        target_columns: [to.primaryKey],
        kind: rel.kind,
        label: rel.label.trim() || undefined,
      }];
    })
    : undefined;
  const pinnedRows = hasDraftTables ? draftRows : csv(entities);
  const pinnedCols = hasDraftTables ? draftCols : csv(attrs);
  const schemaPinned = hasDraftTables || !!(pinnedRows || pinnedCols);
  const visibleColCount = activeDraft ? (pinnedCols?.length ?? activeDraft.columns.length + 1) : (pinnedCols?.length ?? 0);
  const overrideChip = [
    overrides.effort,
    overrides.max_time != null ? `${overrides.max_time}s` : null,
  ].filter(Boolean).join(" · ");

  const hero = variant === "hero";
  const slashTyping = /^\/[a-z]*$/i.test(text);
  const matches = slashTyping ? COMMANDS.filter((c) => c.cmd.startsWith(text.toLowerCase())) : [];
  const menuOpen = matches.length > 0 && focused && !menuDismissed;

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  // autosize
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, hero ? 200 : 160)}px`;
  }, [text, hero]);

  const choose = (cmd: string) => {
    if (cmd === "/schema") {
      setShowSchema((v) => !v);
      setText("");
    } else {
      setText(`${cmd} `);
    }
    ref.current?.focus();
  };

  const submit = () => {
    const m = text.trim().match(/^\/(wide|deep|local)\s+([\s\S]+)$/i);
    const body = (m ? m[2] : text).trim();
    if (!body || body.startsWith("/")) return;
    if (running) {
      // Mid-run: steer the live orchestrator rather than queue a new search.
      if (!onSteer) return;
      onSteer(body);
      setText("");
      return;
    }
    onSubmit(body, {
      type: m?.[1]?.toLowerCase(),
      entities: pinnedRows,
      attrs: pinnedCols,
      tableLabel: hasDraftTables ? resolvedEntityName || undefined : undefined,
      primaryKey: hasDraftTables ? [resolvedPrimaryKey] : undefined,
      rowLabel: hasDraftTables ? resolvedEntityName || undefined : undefined,
      tables: schemaTables,
      relations: schemaRelations,
    });
    setText("");
  };

  const clearSchema = () => {
    setEntities("");
    setAttrs("");
    setTableDrafts([]);
    setRelationDrafts([]);
    setActiveDraftId(null);
    setShowSchema(false);
  };

  const drawPoint = (e: PointerEvent<HTMLDivElement>): DrawPoint => {
    const rect = e.currentTarget.getBoundingClientRect();
    return {
      x: clamp(e.clientX - rect.left, 0, rect.width),
      y: clamp(e.clientY - rect.top, 0, rect.height),
    };
  };

  const drawPreview = (a: DrawPoint, b: DrawPoint): DrawPreview => {
    const width = Math.abs(b.x - a.x);
    const height = Math.abs(b.y - a.y);
    const cols = clamp(Math.round(width / DRAW_CELL_W), 2, 8);
    const rows = clamp(Math.round(height / DRAW_CELL_H), 1, 12);
    return {
      x: Math.min(a.x, b.x),
      y: Math.min(a.y, b.y),
      width,
      height,
      rows,
      cols,
    };
  };

  const preview = dragStart && dragNow ? drawPreview(dragStart, dragNow) : null;

  const startDrawing = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const point = drawPoint(e);
    setDragStart(point);
    setDragNow(point);
  };

  const moveDrawing = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    setDragNow(drawPoint(e));
  };

  const finishDrawing = () => {
    if (preview && preview.width >= MIN_DRAW_SIZE && preview.height >= MIN_DRAW_SIZE) {
      const draft = makeDraft(preview.rows, Math.max(1, preview.cols - 1), tableDrafts.length);
      setTableDrafts((drafts) => [...drafts, draft]);
      setActiveDraftId(draft.id);
    }
    setDragStart(null);
    setDragNow(null);
  };

  const updateDraft = (patch: Partial<TableDraft>) => {
    if (!activeDraftId) return;
    setTableDrafts((drafts) => drafts.map((draft) => draft.id === activeDraftId ? { ...draft, ...patch } : draft));
  };

  const removeDraft = (id: string) => {
    setTableDrafts((drafts) => {
      const next = drafts.filter((draft) => draft.id !== id);
      if (activeDraftId === id) setActiveDraftId(next[0]?.id ?? null);
      return next;
    });
    setRelationDrafts((drafts) => drafts.filter((draft) => draft.fromDraftId !== id && draft.toDraftId !== id));
  };

  const addRelation = () => {
    if (tableDrafts.length < 2) return;
    const from = tableDrafts[1] ?? tableDrafts[0];
    const to = tableDrafts[0];
    const fromColumn = cleanList(from.columns)?.[0] ?? draftPrimaryKey(from);
    setRelationDrafts((drafts) => [
      ...drafts,
      {
        id: `rel_${Date.now()}_${drafts.length}`,
        fromDraftId: from.id,
        fromColumn,
        toDraftId: to.id,
        kind: "one_to_many",
        label: "",
      },
    ]);
  };

  const updateRelation = (id: string, patch: Partial<RelationDraft>) => {
    setRelationDrafts((drafts) => drafts.map((draft) => draft.id === id ? { ...draft, ...patch } : draft));
  };

  const removeRelation = (id: string) => {
    setRelationDrafts((drafts) => drafts.filter((draft) => draft.id !== id));
  };

  const updateDraftRow = (index: number, value: string) => {
    if (!activeDraft) return;
    const rows = [...activeDraft.rows];
    rows[index] = value;
    updateDraft({ rows });
  };

  const updateDraftColumn = (index: number, value: string) => {
    if (!activeDraft) return;
    const columns = [...activeDraft.columns];
    columns[index] = value;
    updateDraft({ columns });
  };

  const addDraftRow = () => {
    if (!activeDraft) return;
    updateDraft({ rows: [...activeDraft.rows, ""] });
  };

  const addDraftColumn = () => {
    if (!activeDraft) return;
    updateDraft({ columns: [...activeDraft.columns, `字段 ${activeDraft.columns.length + 1}`] });
  };

  const removeDraftColumn = (index: number) => {
    if (!activeDraft || activeDraft.columns.length <= 1) return;
    updateDraft({ columns: activeDraft.columns.filter((_, i) => i !== index) });
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    if (menuOpen) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => (s + 1) % matches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => (s - 1 + matches.length) % matches.length); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); choose(matches[sel].cmd); return; }
      if (e.key === "Escape") { setMenuDismissed(true); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  return (
    <div className="relative w-full">
      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className={`surface flex items-end gap-2 transition-shadow focus-within:border-line-strong ${
          hero ? "rounded-2xl px-4 py-3.5 shadow-[0_2px_18px_rgba(21,34,56,0.06)]" : "rounded-2xl px-3.5 py-2.5"
        }`}
      >
        <button
          type="button"
          onClick={() => setShowSchema((v) => !v)}
          title="Pin table rows & columns (optional)"
          className={`mb-0.5 shrink-0 rounded-lg p-1.5 transition-colors ${
            showSchema || schemaPinned ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"
          }`}
        >
          <SlidersHorizontal size={hero ? 17 : 15} />
        </button>
        <button
          type="button"
          onClick={() => setShowOverrides((v) => !v)}
          title="Run overrides"
          className={`mb-0.5 shrink-0 rounded-lg p-1.5 transition-colors ${
            showOverrides || overridesActive ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"
          }`}
        >
          <Gauge size={hero ? 17 : 15} />
        </button>
        {schemaPinned && !showSchema && (
          <span className="mb-1 flex shrink-0 items-center gap-1 rounded-md bg-clay px-1.5 py-0.5 text-[11px] text-accent-ink">
            {hasDraftTables ? `${tableDrafts.length} tables` : `${pinnedRows?.length ?? 0} rows × ${pinnedCols?.length ?? 0} cols`}
            <button type="button" aria-label="Clear pinned schema" onClick={clearSchema}
              className="rounded-sm transition-opacity hover:opacity-70">
              <X size={11} />
            </button>
          </span>
        )}
        {overridesActive && (
          <span className="mb-1 flex shrink-0 items-center gap-1 rounded-md bg-clay px-1.5 py-0.5 text-[11px] text-accent-ink">
            {overrideChip}
            <button type="button" aria-label="Clear run overrides" onClick={clearOverrides}
              className="rounded-sm transition-opacity hover:opacity-70">
              <X size={11} />
            </button>
          </span>
        )}
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => { setText(e.target.value); setSel(0); setMenuDismissed(false); }}
          onKeyDown={onKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          spellCheck={false}
          placeholder={
            running
              ? onSteer
                ? "Searching… press Enter to steer the live run"
                : "Searching… type your next question"
              : placeholder ?? "Ask anything…"
          }
          className={`min-w-0 flex-1 resize-none bg-transparent leading-relaxed text-ink caret-accent outline-none placeholder:text-ink-faint disabled:opacity-50 ${
            hero ? "py-1 text-[16px]" : "py-0.5 text-[15px]"
          }`}
        />
        {running && onStop && (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop the run"
            title="Stop the run"
            className={`mb-0.5 shrink-0 rounded-xl border border-err/40 text-err transition-colors hover:bg-err/10 ${
              hero ? "p-2.5" : "p-2"
            }`}
          >
            <Square size={hero ? 16 : 14} fill="currentColor" />
          </button>
        )}
        <button
          type="submit"
          disabled={!text.trim() || (running && !onSteer)}
          aria-label={running && onSteer ? "Steer the live run" : "Send"}
          title={running && onSteer ? "Steer the live run" : undefined}
          className={`mb-0.5 shrink-0 rounded-xl bg-accent text-white transition-opacity hover:opacity-90 disabled:opacity-25 ${
            hero ? "p-2.5" : "p-2"
          }`}
        >
          <ArrowUp size={hero ? 18 : 16} />
        </button>
      </form>

      {/* manual schema row */}
      {showSchema && (
        <div className="rise-in mt-2">
          {hasDraftTables && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              {tableDrafts.map((draft, i) => {
                const label = draft.entityName.trim() || `Table ${i + 1}`;
                const active = draft.id === activeDraftId;
                return (
                  <div
                    key={draft.id}
                    className={`flex items-center rounded-lg border text-[12px] transition-colors ${
                      active
                        ? "border-line-strong bg-clay text-accent-ink"
                        : "border-line bg-surface text-ink-dim hover:bg-surface-2"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setActiveDraftId(draft.id)}
                      className="flex min-w-0 items-center gap-1 px-2 py-1"
                    >
                      <Table2 size={12} />
                      <span className="max-w-24 truncate">{label}</span>
                    </button>
                    {tableDrafts.length > 1 && (
                      <button
                        type="button"
                        aria-label="Remove table"
                        onClick={() => removeDraft(draft.id)}
                        className="mr-1 rounded-sm p-0.5 text-ink-faint hover:text-ink-dim"
                      >
                        <X size={11} />
                      </button>
                    )}
                  </div>
                );
              })}
              <button
                type="button"
                onClick={() => setActiveDraftId(null)}
                className="flex items-center gap-1 rounded-lg border border-line bg-surface px-2 py-1 text-[12px] text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink-dim"
              >
                <Plus size={12} />
                Table
              </button>
            </div>
          )}

          {activeDraft ? (
            <div className="surface overflow-hidden rounded-xl">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 text-[13px]">
                <label className="flex min-w-[180px] flex-1 items-center gap-2">
                  <span className="shrink-0 text-ink-faint">Entity</span>
                  <input
                    autoFocus
                    value={activeDraft.entityName}
                    onChange={(e) => updateDraft({ entityName: e.target.value })}
                    placeholder="客户"
                    spellCheck={false}
                    className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint"
                  />
                </label>
                <label className="flex min-w-[170px] flex-1 items-center gap-2">
                  <KeyRound size={13} className="shrink-0 text-accent-ink" />
                  <input
                    value={activeDraft.primaryKey}
                    onChange={(e) => updateDraft({ primaryKey: e.target.value })}
                    placeholder={resolvedEntityName ? `${resolvedEntityName} ID` : "ID"}
                    spellCheck={false}
                    className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => removeDraft(activeDraft.id)}
                  className="rounded-lg px-2 py-1 text-[12px] text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim"
                >
                  Redraw
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full table-fixed border-collapse text-[13px]">
                  <thead>
                    <tr className="border-b border-line bg-surface-2/60">
                      <th className="w-36 border-r border-line px-2 py-1.5 text-left font-medium text-ink">
                        <div className="flex items-center gap-1.5">
                          <KeyRound size={13} className="shrink-0 text-accent-ink" />
                          <span className="truncate">{resolvedPrimaryKey}</span>
                        </div>
                      </th>
                      {activeDraft.columns.map((col, i) => (
                        <th key={i} className="w-36 border-r border-line px-2 py-1.5 text-left font-medium">
                          <div className="flex items-center gap-1">
                            <input
                              value={col}
                              onChange={(e) => updateDraftColumn(i, e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Tab" && !e.shiftKey && i === activeDraft.columns.length - 1) {
                                  addDraftColumn();
                                }
                              }}
                              spellCheck={false}
                              className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint"
                            />
                            <button
                              type="button"
                              aria-label="Remove column"
                              onClick={() => removeDraftColumn(i)}
                              disabled={activeDraft.columns.length <= 1}
                              className="rounded p-0.5 text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim disabled:opacity-20"
                            >
                              <X size={11} />
                            </button>
                          </div>
                        </th>
                      ))}
                      <th className="w-10 px-1 py-1.5">
                        <button
                          type="button"
                          aria-label="Add column"
                          onClick={addDraftColumn}
                          className="rounded-md p-1 text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim"
                        >
                          <Plus size={13} />
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeDraft.rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="border-b border-line last:border-b-0">
                        <td className="border-r border-line px-2 py-1.5">
                          <input
                            value={row}
                            onChange={(e) => updateDraftRow(rowIndex, e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && rowIndex === activeDraft.rows.length - 1) {
                                e.preventDefault();
                                addDraftRow();
                              }
                            }}
                            placeholder={`实体 ${rowIndex + 1}`}
                            spellCheck={false}
                            className="w-full bg-transparent font-medium text-ink outline-none placeholder:text-ink-faint"
                          />
                        </td>
                        {activeDraft.columns.map((_, colIndex) => (
                          <td key={colIndex} className="border-r border-line px-2 py-1.5 text-ink-faint">
                            —
                          </td>
                        ))}
                        <td />
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={activeDraft.columns.length + 2} className="px-2 py-1.5">
                        <button
                          type="button"
                          onClick={addDraftRow}
                          className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[12px] text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim"
                        >
                          <Plus size={12} />
                          Row
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <>
              <div
                onPointerDown={startDrawing}
                onPointerMove={moveDrawing}
                onPointerUp={finishDrawing}
                onPointerCancel={finishDrawing}
                className="surface relative h-44 cursor-crosshair overflow-hidden rounded-xl bg-surface-2/45"
              >
                <div className="pointer-events-none absolute left-3 top-2 flex items-center gap-2 text-[12px] text-ink-faint">
                  <Table2 size={14} />
                  <span>Drag table area</span>
                </div>
                {preview && (
                  <div
                    className="pointer-events-none absolute grid overflow-hidden rounded-lg border border-accent bg-accent/10 shadow-sm"
                    style={{
                      left: preview.x,
                      top: preview.y,
                      width: preview.width,
                      height: preview.height,
                      gridTemplateColumns: `repeat(${preview.cols}, minmax(0, 1fr))`,
                      gridTemplateRows: `repeat(${preview.rows + 1}, minmax(0, 1fr))`,
                    }}
                  >
                    {Array.from({ length: preview.cols * (preview.rows + 1) }).map((_, i) => (
                      <div key={i} className="border-b border-r border-accent/35" />
                    ))}
                    <div className="absolute right-1 top-1 rounded bg-accent px-1.5 py-0.5 text-[11px] text-white">
                      {preview.rows} × {preview.cols}
                    </div>
                  </div>
                )}
              </div>
              {!hasDraftTables && (
                <div className="grid grid-cols-2 gap-2 text-[13px]">
                  <label className="surface flex items-center gap-2 rounded-xl px-3 py-2 focus-within:border-line-strong">
                    <span className="shrink-0 text-ink-faint">Rows</span>
                    <input
                      autoFocus
                      value={entities}
                      onChange={(e) => setEntities(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
                      placeholder="Tesla, BYD, NIO"
                      spellCheck={false}
                      className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
                    />
                  </label>
                  <label className="surface flex items-center gap-2 rounded-xl px-3 py-2 focus-within:border-line-strong">
                    <span className="shrink-0 text-ink-faint">Cols</span>
                    <input
                      value={attrs}
                      onChange={(e) => setAttrs(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
                      placeholder="price, range, 0-100 km/h"
                      spellCheck={false}
                      className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
                    />
                  </label>
                </div>
              )}
            </>
          )}

          {hasDraftTables && (
            <div className="surface mt-2 rounded-xl px-3 py-2">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[12px] font-medium text-ink-dim">Relations</span>
                <button
                  type="button"
                  onClick={addRelation}
                  disabled={tableDrafts.length < 2}
                  className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[12px] text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim disabled:opacity-30"
                >
                  <Plus size={12} />
                  Relation
                </button>
              </div>
              {relationDrafts.length > 0 ? (
                <div className="space-y-1.5">
                  {relationDrafts.map((rel) => {
                    const fromMeta = tableMetaByDraftId.get(rel.fromDraftId) ?? tableMetas[0];
                    const toMeta = tableMetaByDraftId.get(rel.toDraftId) ?? tableMetas[0];
                    const fromAttrs = fromMeta?.attrs ?? [];
                    return (
                      <div key={rel.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-1.5 text-[12px]">
                        <Select
                          value={rel.fromDraftId}
                          onChange={(value) => {
                            const nextFrom = tableMetaByDraftId.get(value);
                            updateRelation(rel.id, {
                              fromDraftId: value,
                              fromColumn: nextFrom?.attrs.find((attr) => attr !== nextFrom.primaryKey) ?? nextFrom?.primaryKey ?? "",
                            });
                          }}
                          options={tableMetas.map((meta) => ({ value: meta.draft.id, label: meta.label }))}
                          ariaLabel="Source table"
                          className="w-full"
                          size="sm"
                        />
                        <Select
                          value={fromAttrs.includes(rel.fromColumn) ? rel.fromColumn : fromAttrs[0] ?? ""}
                          onChange={(value) => updateRelation(rel.id, { fromColumn: value })}
                          options={fromAttrs.map((attr) => ({ value: attr, label: attr }))}
                          ariaLabel="Foreign key column"
                          className="w-full"
                          size="sm"
                        />
                        <Select
                          value={rel.toDraftId}
                          onChange={(value) => updateRelation(rel.id, { toDraftId: value })}
                          options={tableMetas.map((meta) => ({
                            value: meta.draft.id,
                            label: `${meta.label}.${meta.primaryKey}`,
                          }))}
                          ariaLabel="Target table and primary key"
                          className="w-full"
                          size="sm"
                        />
                        <div className="flex items-center gap-1">
                          <Select
                            value={rel.kind}
                            onChange={(value) => updateRelation(rel.id, { kind: value as RelationDraft["kind"] })}
                            options={[
                              { value: "one_to_many", label: "1:N" },
                              { value: "many_to_many", label: "N:N" },
                            ]}
                            ariaLabel="Relation type"
                            size="sm"
                          />
                          <button
                            type="button"
                            aria-label="Remove relation"
                            onClick={() => removeRelation(rel.id)}
                            className="rounded-md p-1 text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim"
                          >
                            <X size={12} />
                          </button>
                        </div>
                        <input
                          value={rel.label}
                          onChange={(e) => updateRelation(rel.id, { label: e.target.value })}
                          placeholder={`${fromMeta?.label ?? "From"} -> ${toMeta?.label ?? "To"}`}
                          spellCheck={false}
                          className="col-span-4 rounded-md border border-line bg-surface px-2 py-1 text-ink outline-none placeholder:text-ink-faint"
                        />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-line px-2 py-2 text-[12px] text-ink-faint">
                  Add a relation after creating at least two tables.
                </div>
              )}
            </div>
          )}

          <div className="mt-1.5 flex items-baseline justify-between px-1 text-[11.5px] text-ink-faint">
            <span>{hasDraftTables ? `${tableDrafts.length} tables · ${relationDrafts.length} relations · ${pinnedRows?.length ?? 0} primary values × ${visibleColCount} columns in current table` : "Optional — pin the table's rows and columns (comma-separated). Leave empty and the orchestrator designs the schema itself."}</span>
            {schemaPinned && (
              <button type="button" onClick={clearSchema} className="shrink-0 pl-3 text-ink-faint transition-colors hover:text-ink-dim">
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {/* per-run overrides popover */}
      {showOverrides && (
        <RunOverridesPopover direction={hero ? "down" : "up"} onClose={() => setShowOverrides(false)} />
      )}

      {/* slash menu */}
      {menuOpen && (
        <div className="surface absolute inset-x-0 top-full z-20 mt-2 overflow-hidden rounded-xl shadow-xl">
          {matches.map((c, i) => (
            <button
              key={c.cmd}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(c.cmd)}
              onMouseEnter={() => setSel(i)}
              className={`flex w-full items-baseline gap-3 px-4 py-2 text-left text-[13px] ${i === sel ? "bg-clay/50" : ""}`}
            >
              <span className={`w-16 shrink-0 font-mono ${i === sel ? "text-accent-ink" : "text-ink-dim"}`}>{c.cmd}</span>
              <span className="truncate text-ink-faint">{c.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
