"use client";

import { useEffect, useId, useMemo, useReducer, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import {
  AlertCircle,
  ArrowUp,
  ClipboardPaste,
  Gauge,
  KeyRound,
  Link2,
  Loader2,
  Minus,
  Plus,
  Redo2,
  SlidersHorizontal,
  Square,
  Table2,
  Undo2,
  X,
} from "lucide-react";

import { useSettings } from "@/components/settings/SettingsProvider";
import RunOverridesPopover from "@/components/settings/RunOverridesPopover";
import Select from "@/components/ui/Select";
import {
  parseDelimitedTable,
  validateSchemaDrafts,
  type RelationDraft,
  type SchemaSnapshot,
  type TableDraft,
} from "@/lib/schemaDraft";

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
  stopping?: boolean;
  running?: boolean;
  /** "hero" = large landing composer, "bar" = compact in-conversation bar */
  variant?: "hero" | "bar";
  placeholder?: string;
  autoFocus?: boolean;
  focusRequest?: number;
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

type DrawPoint = {
  x: number;
  y: number;
};

type DrawPreview = DrawPoint & {
  width: number;
  height: number;
  dragWidth: number;
  dragHeight: number;
  rows: number;
  cols: number;
};

const DRAW_CELL_W = 108;
const DRAW_CELL_H = 34;
const MIN_DRAW_SIZE = 26;
const HISTORY_LIMIT = 60;

type SchemaHistoryState = {
  past: SchemaSnapshot[];
  present: SchemaSnapshot;
  future: SchemaSnapshot[];
  mergeKey: string | null;
};

type SchemaHistoryAction =
  | { type: "commit"; update: (snapshot: SchemaSnapshot) => SchemaSnapshot; mergeKey?: string }
  | { type: "break" }
  | { type: "undo" }
  | { type: "redo" };

const EMPTY_SCHEMA: SchemaSnapshot = { tableDrafts: [], relationDrafts: [] };

function schemaHistoryReducer(state: SchemaHistoryState, action: SchemaHistoryAction): SchemaHistoryState {
  if (action.type === "commit") {
    const next = action.update(state.present);
    if (next === state.present) return state;
    if (action.mergeKey && action.mergeKey === state.mergeKey) {
      return { ...state, present: next, future: [] };
    }
    return {
      past: [...state.past, state.present].slice(-HISTORY_LIMIT),
      present: next,
      future: [],
      mergeKey: action.mergeKey ?? null,
    };
  }
  if (action.type === "break") return state.mergeKey ? { ...state, mergeKey: null } : state;
  if (action.type === "undo") {
    const previous = state.past.at(-1);
    if (!previous) return state;
    return {
      past: state.past.slice(0, -1),
      present: previous,
      future: [state.present, ...state.future],
      mergeKey: null,
    };
  }
  const next = state.future[0];
  if (!next) return state;
  return {
    past: [...state.past, state.present].slice(-HISTORY_LIMIT),
    present: next,
    future: state.future.slice(1),
    mergeKey: null,
  };
}

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));

const cleanList = (items: string[]) => {
  const cleaned = items.map((x) => x.trim()).filter(Boolean);
  return cleaned.length ? cleaned : undefined;
};

const countLabel = (count: number, singular: string, plural = `${singular}s`) => `${count} ${count === 1 ? singular : plural}`;

const makeDraft = (rows: number, dataCols: number, id: string): TableDraft => ({
  id,
  entityName: "",
  primaryKey: "ID",
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
  stopping = false,
  running = false,
  variant = "bar",
  placeholder,
  autoFocus = false,
  focusRequest = 0,
}: Props) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [showSchema, setShowSchema] = useState(false);
  const [showOverrides, setShowOverrides] = useState(false);
  const [entities, setEntities] = useState("");
  const [attrs, setAttrs] = useState("");
  const [schemaHistory, dispatchSchema] = useReducer(schemaHistoryReducer, {
    past: [],
    present: EMPTY_SCHEMA,
    future: [],
    mergeKey: null,
  });
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const [dragStart, setDragStart] = useState<DrawPoint | null>(null);
  const [dragNow, setDragNow] = useState<DrawPoint | null>(null);
  const [showPaste, setShowPaste] = useState(false);
  const [pasteEntityName, setPasteEntityName] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [sel, setSel] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const schemaIdPrefix = useId().replace(/[^a-z0-9]/gi, "");
  const schemaIdCounter = useRef(0);
  const { overrides, clearOverrides } = useSettings();
  const { tableDrafts, relationDrafts } = schemaHistory.present;
  const schemaValidation = useMemo(
    () => validateSchemaDrafts(tableDrafts, relationDrafts),
    [relationDrafts, tableDrafts],
  );
  const schemaInvalid = tableDrafts.length > 0 && !schemaValidation.valid;
  const pasteResult = useMemo(() => parseDelimitedTable(pasteText), [pasteText]);
  const issueFor = (key: string) => schemaValidation.byKey[key]?.[0];
  const tablesWithIssues = new Set(
    schemaValidation.issues.flatMap((issue) => issue.key.startsWith("table:") ? [issue.key.split(":")[1]] : []),
  );

  const overridesActive = overrides.effort != null || overrides.max_time != null;
  // Pinned schema follows the *content*, not the panel visibility — collapsing
  // the panel must not silently drop what the user typed.
  const resolvedActiveDraftId = activeDraftId && tableDrafts.some((draft) => draft.id === activeDraftId)
    ? activeDraftId
    : tableDrafts[0]?.id ?? null;
  const activeDraft = tableDrafts.find((draft) => draft.id === resolvedActiveDraftId) ?? null;
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

  const commitSchema = (update: (snapshot: SchemaSnapshot) => SchemaSnapshot, mergeKey?: string) => {
    dispatchSchema({ type: "commit", update, mergeKey });
  };
  const breakSchemaMerge = () => dispatchSchema({ type: "break" });
  const nextSchemaId = (kind: "draft" | "rel") => {
    schemaIdCounter.current += 1;
    return `${kind}_${schemaIdPrefix}_${schemaIdCounter.current}`;
  };

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    if (focusRequest > 0) ref.current?.focus();
  }, [focusRequest]);

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
    if (hasDraftTables && !schemaValidation.valid) {
      setShowSchema(true);
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
    if (hasDraftTables || relationDrafts.length > 0) {
      commitSchema(() => EMPTY_SCHEMA);
    }
    setActiveDraftId(null);
    setShowPaste(false);
    setPasteEntityName("");
    setPasteText("");
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
    const dragWidth = Math.abs(b.x - a.x);
    const dragHeight = Math.abs(b.y - a.y);
    const cols = clamp(Math.round(dragWidth / DRAW_CELL_W), 2, 8);
    const rows = clamp(Math.round(dragHeight / DRAW_CELL_H) - 1, 1, 12);
    const width = cols * DRAW_CELL_W;
    const height = (rows + 1) * DRAW_CELL_H;
    return {
      x: b.x >= a.x ? a.x : Math.max(0, a.x - width),
      y: b.y >= a.y ? a.y : Math.max(0, a.y - height),
      width,
      height,
      dragWidth,
      dragHeight,
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
    if (preview && preview.dragWidth >= MIN_DRAW_SIZE && preview.dragHeight >= MIN_DRAW_SIZE) {
      const draft = makeDraft(preview.rows, Math.max(1, preview.cols - 1), nextSchemaId("draft"));
      commitSchema((snapshot) => ({ ...snapshot, tableDrafts: [...snapshot.tableDrafts, draft] }));
      setActiveDraftId(draft.id);
    }
    setDragStart(null);
    setDragNow(null);
  };

  const updateDraft = (patch: Partial<TableDraft>, mergeKey?: string) => {
    if (!resolvedActiveDraftId) return;
    commitSchema((snapshot) => ({
      ...snapshot,
      tableDrafts: snapshot.tableDrafts.map((draft) => draft.id === resolvedActiveDraftId ? { ...draft, ...patch } : draft),
    }), mergeKey);
  };

  const removeDraft = (id: string) => {
    commitSchema((snapshot) => ({
      tableDrafts: snapshot.tableDrafts.filter((draft) => draft.id !== id),
      relationDrafts: snapshot.relationDrafts.filter((draft) => draft.fromDraftId !== id && draft.toDraftId !== id),
    }));
    if (activeDraftId === id) setActiveDraftId(tableDrafts.find((draft) => draft.id !== id)?.id ?? null);
  };

  const addRelation = () => {
    if (tableDrafts.length < 2) return;
    const from = tableDrafts[1] ?? tableDrafts[0];
    const to = tableDrafts[0];
    const fromColumn = cleanList(from.columns)?.[0] ?? draftPrimaryKey(from);
    const relationId = nextSchemaId("rel");
    commitSchema((snapshot) => ({
      ...snapshot,
      relationDrafts: [
        ...snapshot.relationDrafts,
        {
          id: relationId,
          fromDraftId: from.id,
          fromColumn,
          toDraftId: to.id,
          kind: "one_to_many",
          label: "",
        },
      ],
    }));
  };

  const updateRelation = (id: string, patch: Partial<RelationDraft>, mergeKey?: string) => {
    commitSchema((snapshot) => ({
      ...snapshot,
      relationDrafts: snapshot.relationDrafts.map((draft) => draft.id === id ? { ...draft, ...patch } : draft),
    }), mergeKey);
  };

  const removeRelation = (id: string) => {
    commitSchema((snapshot) => ({
      ...snapshot,
      relationDrafts: snapshot.relationDrafts.filter((draft) => draft.id !== id),
    }));
  };

  const updateDraftRow = (index: number, value: string) => {
    if (!activeDraft) return;
    const rows = [...activeDraft.rows];
    rows[index] = value;
    updateDraft({ rows }, `table:${activeDraft.id}:row:${index}`);
  };

  const updateDraftColumn = (index: number, value: string) => {
    if (!activeDraft) return;
    const previous = activeDraft.columns[index];
    commitSchema((snapshot) => ({
      tableDrafts: snapshot.tableDrafts.map((draft) => {
        if (draft.id !== activeDraft.id) return draft;
        const columns = [...draft.columns];
        columns[index] = value;
        return { ...draft, columns };
      }),
      relationDrafts: snapshot.relationDrafts.map((relation) => (
        relation.fromDraftId === activeDraft.id && relation.fromColumn === previous
          ? { ...relation, fromColumn: value }
          : relation
      )),
    }), `table:${activeDraft.id}:column:${index}`);
  };

  const updatePrimaryKey = (value: string) => {
    if (!activeDraft) return;
    const previous = activeDraft.primaryKey;
    commitSchema((snapshot) => ({
      tableDrafts: snapshot.tableDrafts.map((draft) => draft.id === activeDraft.id ? { ...draft, primaryKey: value } : draft),
      relationDrafts: snapshot.relationDrafts.map((relation) => (
        relation.fromDraftId === activeDraft.id && relation.fromColumn === previous
          ? { ...relation, fromColumn: value }
          : relation
      )),
    }), `table:${activeDraft.id}:primary`);
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
    const removed = activeDraft.columns[index];
    const columns = activeDraft.columns.filter((_, i) => i !== index);
    const replacement = columns[0] ?? activeDraft.primaryKey;
    commitSchema((snapshot) => ({
      tableDrafts: snapshot.tableDrafts.map((draft) => draft.id === activeDraft.id ? { ...draft, columns } : draft),
      relationDrafts: snapshot.relationDrafts.map((relation) => (
        relation.fromDraftId === activeDraft.id && relation.fromColumn === removed
          ? { ...relation, fromColumn: replacement }
          : relation
      )),
    }));
  };

  const resizeRows = (count: number) => {
    if (!activeDraft) return;
    const nextCount = clamp(count, 1, 50);
    const rows = Array.from({ length: nextCount }, (_, index) => activeDraft.rows[index] ?? "");
    updateDraft({ rows });
  };

  const resizeColumns = (count: number) => {
    if (!activeDraft) return;
    const nextCount = clamp(count, 1, 20);
    const columns = Array.from(
      { length: nextCount },
      (_, index) => activeDraft.columns[index] ?? `字段 ${index + 1}`,
    );
    const validColumns = new Set([activeDraft.primaryKey, ...columns]);
    commitSchema((snapshot) => ({
      tableDrafts: snapshot.tableDrafts.map((draft) => draft.id === activeDraft.id ? { ...draft, columns } : draft),
      relationDrafts: snapshot.relationDrafts.map((relation) => (
        relation.fromDraftId === activeDraft.id && !validColumns.has(relation.fromColumn)
          ? { ...relation, fromColumn: columns[0] ?? activeDraft.primaryKey }
          : relation
      )),
    }));
  };

  const importPastedTable = () => {
    if (!pasteResult.ok || !pasteEntityName.trim()) return;
    const draft: TableDraft = {
      id: nextSchemaId("draft"),
      entityName: pasteEntityName.trim(),
      primaryKey: pasteResult.table.headers[0],
      rows: pasteResult.table.rows.map((row) => row[0]).filter(Boolean),
      columns: pasteResult.table.headers.slice(1),
    };
    commitSchema((snapshot) => ({ ...snapshot, tableDrafts: [...snapshot.tableDrafts, draft] }));
    setActiveDraftId(draft.id);
    setPasteEntityName("");
    setPasteText("");
    setShowPaste(false);
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
          aria-label="Edit table schema"
          className={`mb-0.5 shrink-0 rounded-lg p-1.5 transition-colors ${
            schemaInvalid
              ? "bg-err/10 text-err"
              : showSchema || schemaPinned ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"
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
          <span className={`mb-1 flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] ${schemaInvalid ? "bg-err/10 text-err" : "bg-clay text-accent-ink"}`}>
            {schemaInvalid && <AlertCircle size={11} />}
            {hasDraftTables
              ? countLabel(tableDrafts.length, "table")
              : `${countLabel(pinnedRows?.length ?? 0, "row")} × ${countLabel(pinnedCols?.length ?? 0, "col")}`}
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
            disabled={stopping}
            aria-label={stopping ? "Stopping the run" : "Stop the run"}
            title={stopping ? "Stopping the run" : "Stop the run"}
            className={`mb-0.5 shrink-0 rounded-xl border border-err/40 text-err transition-colors hover:bg-err/10 disabled:cursor-wait disabled:opacity-60 ${
              hero ? "p-2.5" : "p-2"
            }`}
          >
            {stopping ? (
              <Loader2 className="animate-spin" size={hero ? 16 : 14} />
            ) : (
              <Square size={hero ? 16 : 14} fill="currentColor" />
            )}
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
          <div className="mb-2 flex items-start gap-2">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
              {tableDrafts.map((draft, i) => {
                const label = draft.entityName.trim() || `Table ${i + 1}`;
                const active = draft.id === resolvedActiveDraftId;
                const invalid = tablesWithIssues.has(draft.id);
                return (
                  <div
                    key={draft.id}
                    className={`flex items-center rounded-lg border text-[12px] transition-colors ${
                      invalid
                        ? "border-err/40 bg-err/5 text-err"
                        : active
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
                      {invalid && <AlertCircle size={11} />}
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
              {hasDraftTables && (
                <button
                  type="button"
                  onClick={() => setActiveDraftId(null)}
                  className="flex items-center gap-1 rounded-lg border border-line bg-surface px-2 py-1 text-[12px] text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink-dim"
                >
                  <Plus size={12} />
                  Table
                </button>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              <button type="button" onClick={() => setShowPaste((value) => !value)}
                aria-label="Paste CSV or TSV" title="Paste CSV or TSV"
                className={`grid h-7 w-7 place-items-center rounded-md transition-colors ${showPaste ? "bg-clay text-accent-ink" : "text-ink-faint hover:bg-surface-2 hover:text-ink"}`}>
                <ClipboardPaste size={14} />
              </button>
              <button type="button" onClick={() => dispatchSchema({ type: "undo" })}
                disabled={schemaHistory.past.length === 0} aria-label="Undo schema change" title="Undo"
                className="grid h-7 w-7 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-25">
                <Undo2 size={14} />
              </button>
              <button type="button" onClick={() => dispatchSchema({ type: "redo" })}
                disabled={schemaHistory.future.length === 0} aria-label="Redo schema change" title="Redo"
                className="grid h-7 w-7 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-25">
                <Redo2 size={14} />
              </button>
            </div>
          </div>

          {showPaste && (
            <div className="surface mb-2 overflow-hidden rounded-xl">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
                <label className="flex min-w-[190px] flex-1 items-center gap-2 text-[12px]">
                  <span className="shrink-0 text-ink-faint">Entity</span>
                  <input value={pasteEntityName} onChange={(event) => setPasteEntityName(event.target.value)}
                    placeholder="Customers" autoFocus spellCheck={false}
                    className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint" />
                </label>
                {pasteResult.ok && (
                  <span className="text-[11px] text-ink-faint">
                    {pasteResult.table.rows.length} rows · {pasteResult.table.headers.length} columns · {pasteResult.table.delimiter === "\t" ? "TSV" : "CSV"}
                  </span>
                )}
              </div>
              <textarea value={pasteText} onChange={(event) => setPasteText(event.target.value)} rows={4}
                placeholder={'customer_id,name,region\nC-001,Acme,APAC'} spellCheck={false}
                className="block w-full resize-y bg-transparent px-3 py-2 font-mono text-[12px] leading-5 text-ink outline-none placeholder:text-ink-faint" />
              <div className="flex items-center gap-2 border-t border-line px-3 py-2">
                {pasteText && !pasteResult.ok && <span role="alert" className="min-w-0 flex-1 text-[11px] text-err">{pasteResult.error}</span>}
                {!pasteText && <span className="min-w-0 flex-1 text-[11px] text-ink-faint">CSV / TSV</span>}
                <button type="button" onClick={() => { setShowPaste(false); setPasteText(""); setPasteEntityName(""); }}
                  className="rounded-md px-2 py-1 text-[12px] text-ink-faint hover:bg-surface-2 hover:text-ink">Cancel</button>
                <button type="button" onClick={importPastedTable} disabled={!pasteResult.ok || !pasteEntityName.trim()}
                  className="rounded-md bg-accent px-2.5 py-1 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30">Create table</button>
              </div>
            </div>
          )}

          {activeDraft ? (
            <div className="surface overflow-hidden rounded-xl">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 text-[13px]">
                <label title={issueFor(`table:${activeDraft.id}:entity`)} className={`flex min-w-[180px] flex-1 items-center gap-2 rounded-md px-2 py-1 ${issueFor(`table:${activeDraft.id}:entity`) ? "bg-err/5 text-err ring-1 ring-err/35" : ""}`}>
                  <span className="shrink-0 text-ink-faint">Entity</span>
                  <input
                    autoFocus
                    value={activeDraft.entityName}
                    onChange={(e) => updateDraft({ entityName: e.target.value }, `table:${activeDraft.id}:entity`)}
                    onBlur={breakSchemaMerge}
                    placeholder="客户"
                    aria-invalid={!!issueFor(`table:${activeDraft.id}:entity`)}
                    spellCheck={false}
                    className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint"
                  />
                </label>
                <label title={issueFor(`table:${activeDraft.id}:primary`)} className={`flex min-w-[170px] flex-1 items-center gap-2 rounded-md px-2 py-1 ${issueFor(`table:${activeDraft.id}:primary`) ? "bg-err/5 text-err ring-1 ring-err/35" : ""}`}>
                  <KeyRound size={13} className="shrink-0 text-accent-ink" />
                  <input
                    value={activeDraft.primaryKey}
                    onChange={(e) => updatePrimaryKey(e.target.value)}
                    onBlur={breakSchemaMerge}
                    placeholder={resolvedEntityName ? `${resolvedEntityName} ID` : "ID"}
                    aria-label="Primary key column"
                    aria-invalid={!!issueFor(`table:${activeDraft.id}:primary`)}
                    spellCheck={false}
                    className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint"
                  />
                </label>
                <div className="flex items-center gap-2 text-[11px] text-ink-faint">
                  <span className="flex items-center rounded-md border border-line bg-surface-2/50">
                    <span className="px-1.5">Rows</span>
                    <button type="button" onClick={() => resizeRows(activeDraft.rows.length - 1)} disabled={activeDraft.rows.length <= 1}
                      aria-label="Remove last row" title="Remove last row" className="grid h-6 w-6 place-items-center border-l border-line hover:bg-clay hover:text-ink disabled:opacity-25"><Minus size={11} /></button>
                    <span className="min-w-6 border-l border-line px-1 text-center font-mono text-ink-dim">{activeDraft.rows.length}</span>
                    <button type="button" onClick={() => resizeRows(activeDraft.rows.length + 1)}
                      aria-label="Add row" title="Add row" className="grid h-6 w-6 place-items-center border-l border-line hover:bg-clay hover:text-ink"><Plus size={11} /></button>
                  </span>
                  <span className="flex items-center rounded-md border border-line bg-surface-2/50">
                    <span className="px-1.5">Cols</span>
                    <button type="button" onClick={() => resizeColumns(activeDraft.columns.length - 1)} disabled={activeDraft.columns.length <= 1}
                      aria-label="Remove last column" title="Remove last column" className="grid h-6 w-6 place-items-center border-l border-line hover:bg-clay hover:text-ink disabled:opacity-25"><Minus size={11} /></button>
                    <span className="min-w-6 border-l border-line px-1 text-center font-mono text-ink-dim">{activeDraft.columns.length + 1}</span>
                    <button type="button" onClick={() => resizeColumns(activeDraft.columns.length + 1)}
                      aria-label="Add column" title="Add column" className="grid h-6 w-6 place-items-center border-l border-line hover:bg-clay hover:text-ink"><Plus size={11} /></button>
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => removeDraft(activeDraft.id)}
                  className="rounded-lg px-2 py-1 text-[12px] text-ink-faint transition-colors hover:bg-clay hover:text-ink-dim"
                >
                  Redraw
                </button>
              </div>
              {(issueFor(`table:${activeDraft.id}:entity`) || issueFor(`table:${activeDraft.id}:primary`)) && (
                <div role="alert" className="flex flex-wrap gap-x-3 gap-y-1 border-b border-err/20 bg-err/5 px-3 py-1.5 text-[11px] text-err">
                  {issueFor(`table:${activeDraft.id}:entity`) && <span>{issueFor(`table:${activeDraft.id}:entity`)}</span>}
                  {issueFor(`table:${activeDraft.id}:primary`) && <span>{issueFor(`table:${activeDraft.id}:primary`)}</span>}
                </div>
              )}
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
                        <th key={i} title={issueFor(`table:${activeDraft.id}:column:${i}`)} className={`w-36 border-r px-2 py-1.5 text-left font-medium ${issueFor(`table:${activeDraft.id}:column:${i}`) ? "border-err/40 bg-err/5" : "border-line"}`}>
                          <div className="flex items-center gap-1">
                            <input
                              value={col}
                              onChange={(e) => updateDraftColumn(i, e.target.value)}
                              onBlur={breakSchemaMerge}
                              aria-invalid={!!issueFor(`table:${activeDraft.id}:column:${i}`)}
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
                        <td title={issueFor(`table:${activeDraft.id}:row:${rowIndex}`)} className={`border-r px-2 py-1.5 ${issueFor(`table:${activeDraft.id}:row:${rowIndex}`) ? "border-err/40 bg-err/5" : "border-line"}`}>
                          <input
                            value={row}
                            onChange={(e) => updateDraftRow(rowIndex, e.target.value)}
                            onBlur={breakSchemaMerge}
                            aria-invalid={!!issueFor(`table:${activeDraft.id}:row:${rowIndex}`)}
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
                style={{
                  touchAction: "none",
                  backgroundImage: "linear-gradient(to right, var(--line) 1px, transparent 1px), linear-gradient(to bottom, var(--line) 1px, transparent 1px)",
                  backgroundSize: `${DRAW_CELL_W}px ${DRAW_CELL_H}px`,
                }}
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
                    <div className="absolute right-1 top-1 whitespace-nowrap rounded bg-accent px-1.5 py-0.5 text-[11px] text-white">
                      {preview.rows} rows · {preview.cols} cols
                    </div>
                  </div>
                )}
              </div>
              {!hasDraftTables && (
                <div className="grid grid-cols-1 gap-2 text-[13px] sm:grid-cols-2">
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
                    const relationIssue = issueFor(`relation:${rel.id}`);
                    return (
                      <div key={rel.id} className={`rounded-lg p-1.5 text-[12px] ${relationIssue ? "bg-err/5 ring-1 ring-err/30" : "bg-surface-2/35"}`}>
                        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                          <Select
                            value={rel.fromDraftId}
                            onChange={(value) => {
                              const nextFrom = tableMetaByDraftId.get(value);
                              const nextTarget = value === rel.toDraftId
                                ? tableMetas.find((meta) => meta.draft.id !== value)?.draft.id ?? rel.toDraftId
                                : rel.toDraftId;
                              updateRelation(rel.id, {
                                fromDraftId: value,
                                fromColumn: nextFrom?.attrs.find((attr) => attr !== nextFrom.primaryKey) ?? nextFrom?.primaryKey ?? "",
                                toDraftId: nextTarget,
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
                              disabled: meta.draft.id === rel.fromDraftId,
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
                              className="w-full"
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
                            onChange={(e) => updateRelation(rel.id, { label: e.target.value }, `relation:${rel.id}:label`)}
                            onBlur={breakSchemaMerge}
                            placeholder={`${fromMeta?.label ?? "From"} -> ${toMeta?.label ?? "To"}`}
                            spellCheck={false}
                            className="rounded-md border border-line bg-surface px-2 py-1 text-ink outline-none placeholder:text-ink-faint sm:col-span-4"
                          />
                        </div>
                        {relationIssue && (
                          <div role="alert" className="mt-1 flex items-center gap-1 text-[11px] text-err"><AlertCircle size={11} />{relationIssue}</div>
                        )}
                        {rel.kind === "many_to_many" && !relationIssue && (
                          <div className="mt-1 flex items-center gap-1 text-[11px] text-warn">
                            <Link2 size={11} />
                            Junction semantics: {fromMeta?.label}.{rel.fromColumn} ↔ {toMeta?.label}.{toMeta?.primaryKey}
                          </div>
                        )}
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

          {hasDraftTables && !schemaValidation.valid && (
            <div role="alert" className="mt-2 flex items-start gap-2 rounded-lg border border-err/30 bg-err/5 px-3 py-2 text-[12px] text-err">
              <AlertCircle className="mt-0.5 shrink-0" size={14} />
              <span>{schemaValidation.issues.length} schema {schemaValidation.issues.length === 1 ? "issue" : "issues"} must be fixed before search.</span>
            </div>
          )}

          <div className="mt-1.5 flex items-baseline justify-between px-1 text-[11.5px] text-ink-faint">
            <span>{hasDraftTables
              ? `${countLabel(tableDrafts.length, "table")} · ${countLabel(relationDrafts.length, "relation")} · ${countLabel(pinnedRows?.length ?? 0, "primary value")} × ${countLabel(visibleColCount, "column")} in current table`
              : "Optional — pin the table's rows and columns (comma-separated). Leave empty and the orchestrator designs the schema itself."}</span>
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
