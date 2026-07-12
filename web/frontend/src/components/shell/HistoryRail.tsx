"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Archive,
  ArchiveRestore,
  AlertTriangle,
  Check,
  ChevronDown,
  FolderKanban,
  Inbox,
  Loader2,
  MoreHorizontal,
  PanelLeft,
  PanelLeftClose,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Settings,
  SlidersHorizontal,
  Star,
  Tags,
  Trash2,
  X,
} from "lucide-react";
import { getHealth, type HistoryAssetPatch } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";
import Select from "@/components/ui/Select";

export interface HistoryRailItem {
  id: string;
  title: string;
  status: "running" | "completed" | "incomplete" | "error";
  coverageScore: number | null;
  updatedAt: number;
  project: string;
  tags: string[];
  favorite: boolean;
  archived: boolean;
}

interface Props {
  items: HistoryRailItem[];
  projects: { name: string; count: number }[];
  tags: { name: string; count: number }[];
  assetCounts: { all: number; favorites: number; archived: number; attention: number; unassigned: number };
  activeId: string | null;
  collapsed: boolean;
  searchQuery: string;
  searching?: boolean;
  onSearch: (query: string) => void;
  onToggle: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onUpdateAssets: (id: string, patch: HistoryAssetPatch) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
  loadingId?: string | null;
  mutation?: { id: string; kind: "delete" | "update" } | null;
  historyStatus?: "loading" | "ready" | "error";
  onRetryHistory?: () => void;
}

type View = "all" | "attention" | "favorites" | "archived" | "unassigned" | `project:${string}` | `tag:${string}`;
type SortOrder = "recent" | "oldest" | "title" | "coverage";
type Density = "comfortable" | "compact";
type EditDraft = { title: string; project: string; tags: string };

const DOT: Record<string, string> = {
  running: "bg-accent glow-pulse",
  completed: "bg-ok",
  incomplete: "bg-warn",
  error: "bg-err",
};

function groupLabel(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const value = date.getTime();
  if (value >= startToday) return "Today";
  if (value >= startToday - 6 * 86400000) return "Previous 7 days";
  return "Older";
}

function formatUpdated(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function needsAttention(item: HistoryRailItem): boolean {
  return item.status !== "completed" || (item.coverageScore != null && item.coverageScore < 0.999);
}

export default function HistoryRail({
  items,
  projects,
  tags,
  assetCounts,
  activeId,
  collapsed,
  searchQuery,
  searching = false,
  onSearch,
  onToggle,
  onNew,
  onSelect,
  onUpdateAssets,
  onDelete,
  onOpenSettings,
  loadingId = null,
  mutation = null,
  historyStatus = "ready",
  onRetryHistory,
}: Props) {
  const [health, setHealth] = useState<{ status: string } | null | undefined>(undefined);
  const [view, setView] = useState<View>("all");
  const [sort, setSort] = useState<SortOrder>("recent");
  const [density, setDensity] = useState<Density>("comfortable");
  const [tagsExpanded, setTagsExpanded] = useState(false);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft>({ title: "", project: "", tags: "" });
  const busy = !!loadingId || !!mutation;

  useEffect(() => {
    let alive = true;
    const check = () => getHealth().then((result) => alive && setHealth(result));
    void check();
    const interval = setInterval(check, 15000);
    return () => { alive = false; clearInterval(interval); };
  }, []);

  const setListDensity = (value: Density) => {
    setDensity(value);
  };

  const filtered = useMemo(() => items.filter((item) => {
    if (view === "attention") return !item.archived && needsAttention(item);
    if (view === "favorites") return item.favorite && !item.archived;
    if (view === "archived") return item.archived;
    if (view === "unassigned") return !item.archived && !item.project;
    if (view.startsWith("project:")) return !item.archived && item.project === view.slice(8);
    if (view.startsWith("tag:")) return !item.archived && item.tags.includes(view.slice(4));
    return !item.archived;
  }), [items, view]);

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    if (sort === "oldest") return a.updatedAt - b.updatedAt;
    if (sort === "title") return a.title.localeCompare(b.title);
    if (sort === "coverage") return (a.coverageScore ?? -1) - (b.coverageScore ?? -1);
    return b.updatedAt - a.updatedAt;
  }), [filtered, sort]);

  const groups = useMemo(() => {
    if (searchQuery) return [{ label: "Search results", items: sorted }];
    if (sort === "title") return [{ label: "Alphabetical", items: sorted }];
    if (sort === "coverage") return [{ label: "Lowest coverage first", items: sorted }];
    const result: { label: string; items: HistoryRailItem[] }[] = [];
    const labels = sort === "oldest" ? ["Older", "Previous 7 days", "Today"] : ["Today", "Previous 7 days", "Older"];
    for (const label of labels) {
      const group = sorted.filter((item) => groupLabel(item.updatedAt) === label);
      if (group.length) result.push({ label, items: group });
    }
    return result;
  }, [searchQuery, sort, sorted]);

  const startEdit = (item: HistoryRailItem) => {
    setEditingId(item.id);
    setDraft({ title: item.title, project: item.project, tags: item.tags.join(", ") });
    setMenuId(null);
  };

  const saveEdit = (id: string) => {
    const title = draft.title.trim();
    if (!title || busy) return;
    onUpdateAssets(id, {
      title,
      project: draft.project.trim(),
      tags: draft.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
    });
    setEditingId(null);
  };

  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center gap-3 border-r border-line py-4">
        <button onClick={onToggle} title="Expand" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink"><PanelLeft size={18} /></button>
        <button onClick={onNew} title="New research" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink"><Plus size={18} /></button>
        <button onClick={() => { setView("favorites"); onToggle(); }} title="Favorites" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink"><Star size={18} /></button>
        <span title={health === undefined ? "Connecting" : health ? "Connected" : "Offline"}
          className={`mt-auto h-1.5 w-1.5 rounded-full ${health === undefined ? "bg-warn" : health ? "bg-ok glow-pulse" : "bg-err"}`} />
        <button onClick={onOpenSettings} title="Settings" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink"><Settings size={18} /></button>
      </div>
    );
  }

  const viewButton = (target: View, label: string, icon: ReactNode, count?: number) => (
    <button key={target} type="button" onClick={() => setView(target)}
      className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12.5px] transition-colors ${view === target ? "bg-clay/70 text-ink" : "text-ink-dim hover:bg-surface-2 hover:text-ink"}`}>
      <span className="text-ink-faint">{icon}</span><span className="min-w-0 flex-1 truncate">{label}</span>
      {count !== undefined && count > 0 && <span className="text-[11px] tabular-nums text-ink-faint">{count}</span>}
    </button>
  );

  const renderItem = (item: HistoryRailItem) => {
    const itemLoading = loadingId === item.id;
    const itemMutation = mutation?.id === item.id;
    const coverage = item.coverageScore == null ? null : Math.round(item.coverageScore * 100);
    return (
      <div key={item.id} className="relative">
        <div className={`group relative flex items-start rounded-lg pr-1 transition-colors ${item.id === activeId ? "bg-clay/60" : "hover:bg-surface-2"}`}>
          <button onClick={() => onSelect(item.id)} disabled={busy} aria-busy={itemLoading}
            className={`flex min-w-0 flex-1 items-start gap-2 pl-2.5 text-left disabled:cursor-wait disabled:opacity-70 ${density === "compact" ? "py-1.5" : "py-2"}`}>
            {itemLoading ? <Loader2 className="mt-1 shrink-0 animate-spin text-accent-ink" size={12} />
              : <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${DOT[item.status] ?? "bg-ink-faint"}`} />}
            <span className="min-w-0 flex-1">
              <span className={`block truncate text-[13px] ${item.id === activeId ? "text-ink" : "text-ink-dim group-hover:text-ink"}`}>{item.title}</span>
              <span className={`${density === "compact" ? "hidden" : "mt-0.5 flex"} min-w-0 items-center gap-1.5 text-[10.5px] text-ink-faint`}>
                {item.project && <span className="max-w-24 truncate">{item.project}</span>}
                {item.project && coverage !== null && <span>·</span>}
                {coverage !== null && <span>{coverage}%</span>}
                <span className="ml-auto shrink-0">{formatUpdated(item.updatedAt)}</span>
              </span>
              {density === "comfortable" && item.tags.length > 0 && <span className="mt-1 flex gap-1 overflow-hidden">
                {item.tags.slice(0, 2).map((tag) => <span key={tag} className="max-w-20 truncate rounded bg-surface px-1 py-0.5 text-[9.5px] text-ink-faint">{tag}</span>)}
                {item.tags.length > 2 && <span className="text-[9.5px] text-ink-faint">+{item.tags.length - 2}</span>}
              </span>}
            </span>
          </button>

          {itemMutation ? <Loader2 className="mt-2.5 shrink-0 animate-spin text-ink-faint" size={13} /> : <>
            <button type="button" title={item.favorite ? "Remove from favorites" : "Add to favorites"}
              onClick={() => onUpdateAssets(item.id, { favorite: !item.favorite })}
              className={`mt-1.5 rounded p-1 transition-opacity ${item.favorite ? "text-accent-ink" : "text-ink-faint opacity-0 group-focus-within:opacity-100 group-hover:opacity-100"}`}>
              <Star size={13} fill={item.favorite ? "currentColor" : "none"} />
            </button>
            <button type="button" title="Research actions" onClick={() => setMenuId(menuId === item.id ? null : item.id)}
              className="mt-1.5 rounded p-1 text-ink-faint opacity-0 transition-opacity hover:bg-surface group-focus-within:opacity-100 group-hover:opacity-100">
              <MoreHorizontal size={14} />
            </button>
          </>}
        </div>

        {menuId === item.id && (
          <div className="absolute right-1 top-8 z-20 w-36 rounded-lg border border-line bg-surface p-1 shadow-lg">
            <button type="button" onClick={() => startEdit(item)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><Pencil size={12} /> Edit details</button>
            <button type="button" onClick={() => { onUpdateAssets(item.id, { archived: !item.archived }); setMenuId(null); }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2">
              {item.archived ? <ArchiveRestore size={12} /> : <Archive size={12} />} {item.archived ? "Restore" : "Archive"}
            </button>
            {confirmId === item.id ? <div className="mt-1 flex items-center justify-between border-t border-line px-1 pt-1 text-[11px] text-err">
              Delete?<span><button type="button" title="Confirm delete" onClick={() => onDelete(item.id)} className="rounded p-1 hover:bg-err/10"><Check size={13} /></button>
              <button type="button" title="Cancel delete" onClick={() => setConfirmId(null)} className="rounded p-1 text-ink-faint hover:bg-surface-2"><X size={13} /></button></span>
            </div> : <button type="button" onClick={() => setConfirmId(item.id)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-err hover:bg-err/10"><Trash2 size={12} /> Delete</button>}
          </div>
        )}

        {editingId === item.id && (
          <div className="mx-1 mb-2 mt-1 space-y-2 rounded-lg border border-line bg-surface p-2.5">
            <input autoFocus value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              aria-label="Research title" placeholder="Research title" className="w-full rounded-md border border-line bg-paper px-2 py-1.5 text-[12px] text-ink outline-none focus:border-accent" />
            <div className="relative"><FolderKanban className="absolute left-2 top-2 text-ink-faint" size={12} />
              <input value={draft.project} onChange={(event) => setDraft({ ...draft, project: event.target.value })}
                list="research-projects" aria-label="Project" placeholder="Project (optional)" className="w-full rounded-md border border-line bg-paper py-1.5 pl-7 pr-2 text-[12px] text-ink outline-none focus:border-accent" /></div>
            <div className="relative"><Tags className="absolute left-2 top-2 text-ink-faint" size={12} />
              <input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
                aria-label="Tags" placeholder="Tags, separated by commas" className="w-full rounded-md border border-line bg-paper py-1.5 pl-7 pr-2 text-[12px] text-ink outline-none focus:border-accent" /></div>
            <div className="flex justify-end gap-1.5">
              <button type="button" onClick={() => setEditingId(null)} className="rounded-md px-2 py-1 text-[11px] text-ink-faint hover:bg-surface-2">Cancel</button>
              <button type="button" disabled={!draft.title.trim() || busy} onClick={() => saveEdit(item.id)} className="rounded-md bg-ink px-2 py-1 text-[11px] text-paper disabled:opacity-40">Save</button>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col border-r border-line">
      <datalist id="research-projects">{projects.map((project) => <option key={project.name} value={project.name} />)}</datalist>
      <div className="flex items-center justify-between px-3 pb-2 pt-4">
        <div className="wordmark flex items-center gap-2 px-1 text-[19px]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/searchos-mark.png" alt="" className="h-6 w-6 rounded-md dark:bg-white dark:p-0.5" /> SearchOS
        </div>
        <button onClick={onToggle} title="Collapse" className="rounded-lg p-1.5 text-ink-faint hover:bg-surface-2 hover:text-ink"><PanelLeftClose size={17} /></button>
      </div>

      <div className="px-3 pb-2"><button onClick={onNew}
        className="flex w-full items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 py-2 text-[14px] font-medium text-ink transition-colors hover:bg-surface-2"><Plus size={16} /> New research</button></div>

      <div className="px-3 pb-2">
        <label className="flex items-center gap-2 rounded-lg border border-transparent bg-surface-2/60 px-2.5 py-1.5 text-[13px] text-ink-faint focus-within:border-line">
          {searching ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
          <input value={searchQuery} onChange={(event) => onSearch(event.target.value)} placeholder="Search all research…" aria-label="Search research history"
            className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint" />
          {searchQuery && <button type="button" onClick={() => onSearch("")} aria-label="Clear search" className="rounded p-0.5 hover:bg-surface"><X size={12} /></button>}
        </label>
      </div>

      <div className="px-3 pb-2">
        <div className="space-y-0.5">
          {viewButton("all", "All research", <Inbox size={14} />, assetCounts.all)}
          {viewButton("attention", "Needs review", <AlertTriangle size={14} />, assetCounts.attention)}
          {viewButton("favorites", "Favorites", <Star size={14} />, assetCounts.favorites)}
          {viewButton("archived", "Archived", <Archive size={14} />, assetCounts.archived)}
        </div>
        {(projects.length > 0 || assetCounts.unassigned > 0) && <div className="mt-3">
          <div className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-ink-faint">Projects</div>
          <div className="max-h-28 space-y-0.5 overflow-y-auto">
            {projects.map((project) => viewButton(`project:${project.name}`, project.name, <FolderKanban size={13} />, project.count))}
            {assetCounts.unassigned > 0 && viewButton("unassigned", "Unassigned", <FolderKanban size={13} />, assetCounts.unassigned)}
          </div>
        </div>}
        {tags.length > 0 && <div className="mt-3">
          <div className="flex items-center justify-between px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-ink-faint">
            <span>Tags</span>
            {tags.length > 6 && <button type="button" onClick={() => setTagsExpanded((value) => !value)} aria-label={tagsExpanded ? "Show fewer tags" : "Show all tags"}
              className="rounded p-0.5 hover:bg-surface-2"><ChevronDown size={11} className={`transition-transform ${tagsExpanded ? "rotate-180" : ""}`} /></button>}
          </div>
          <div className={`${tagsExpanded ? "max-h-32 overflow-y-auto" : ""} flex flex-wrap gap-1 px-1`}>
            {(tagsExpanded ? tags : tags.slice(0, 6)).map((tag) => (
              <button key={tag.name} type="button" onClick={() => setView(`tag:${tag.name}`)}
                className={`flex max-w-full items-center gap-1 rounded-md border px-1.5 py-1 text-[10.5px] transition-colors ${view === `tag:${tag.name}` ? "border-line-strong bg-clay text-accent-ink" : "border-line bg-surface text-ink-faint hover:bg-surface-2 hover:text-ink-dim"}`}>
                <span className="max-w-24 truncate">#{tag.name}</span><span className="tabular-nums opacity-70">{tag.count}</span>
              </button>
            ))}
          </div>
        </div>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
        {historyStatus === "error" && <div role="alert" className="mb-2 flex items-start gap-2 rounded-md border border-err/30 bg-err/5 px-2.5 py-2 text-[12px] text-err">
          <span className="min-w-0 flex-1 leading-4">Research history is unavailable</span>
          {onRetryHistory && <button type="button" onClick={onRetryHistory} title="Retry history" className="shrink-0 rounded p-0.5 hover:bg-err/10"><RotateCcw size={13} /></button>}
        </div>}
        {historyStatus !== "loading" && <div className="sticky top-0 z-10 mb-1 flex items-center gap-1 bg-paper/95 px-1 py-1 backdrop-blur-sm">
          <Select
            value={sort}
            onChange={(value) => setSort(value as SortOrder)}
            ariaLabel="Sort research"
            size="sm"
            className="min-w-0 flex-1"
            options={[
              { value: "recent", label: "Recently updated" },
              { value: "oldest", label: "Oldest updated" },
              { value: "title", label: "Title A–Z" },
              { value: "coverage", label: "Lowest coverage" },
            ]}
          />
          <button type="button" onClick={() => setListDensity(density === "compact" ? "comfortable" : "compact")}
            aria-label={density === "compact" ? "Use comfortable list density" : "Use compact list density"}
            title={density === "compact" ? "Comfortable density" : "Compact density"}
            className="grid h-7 w-7 place-items-center rounded-md border border-line bg-surface text-ink-faint hover:bg-surface-2 hover:text-ink"><SlidersHorizontal size={12} /></button>
        </div>}
        {historyStatus === "loading" && items.length === 0 ? <div role="status" className="flex items-center gap-2 px-2 pt-2 text-[12.5px] text-ink-faint"><Loader2 className="animate-spin" size={14} /> Loading research…</div>
          : filtered.length === 0 ? <p className="px-2 pt-2 text-[12.5px] text-ink-faint">{searchQuery ? "No matching research" : view === "archived" ? "No archived research" : "No research here yet"}</p>
          : groups.map((group) => <div key={group.label} className="mb-2"><div className="px-2 pb-1 pt-1 text-[10px] uppercase tracking-wider text-ink-faint">{group.label}</div>{group.items.map(renderItem)}</div>)}
      </div>

      <div className="flex items-center justify-between border-t border-line px-4 py-3 text-[12px] text-ink-faint">
        <span className="flex items-center gap-1.5"><span className={`h-1.5 w-1.5 rounded-full ${health === undefined ? "bg-warn" : health ? "bg-ok glow-pulse" : "bg-err"}`} />{health === undefined ? "Connecting" : health ? "Connected" : "Offline"}</span>
        <span className="flex items-center gap-0.5"><button onClick={onOpenSettings} title="Settings" className="rounded-md p-1.5 text-ink-faint hover:bg-surface-2 hover:text-ink"><Settings size={16} /></button><ThemeToggle /></span>
      </div>
    </div>
  );
}
