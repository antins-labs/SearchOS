"use client";

import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeft, Plus, Search, Pencil, Settings, Trash2, Check, X } from "lucide-react";
import { getHealth } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";

export interface HistoryItem {
  id: string;
  title: string;
  status: "running" | "completed" | "error";
}

interface Props {
  items: HistoryItem[];
  activeId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
}

const DOT: Record<string, string> = {
  running: "bg-accent glow-pulse",
  completed: "bg-ok",
  error: "bg-err",
};

export default function HistoryRail({ items, activeId, collapsed, onToggle, onNew, onSelect, onRename, onDelete, onOpenSettings }: Props) {
  const [q, setQ] = useState("");
  const [health, setHealth] = useState<{ status: string } | null | undefined>(undefined);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const commitRename = (id: string) => {
    const t = editValue.trim();
    if (t) onRename(id, t);
    setEditingId(null);
  };

  useEffect(() => {
    let alive = true;
    const check = () => getHealth().then((h) => alive && setHealth(h));
    check();
    const iv = setInterval(check, 15000);
    return () => { alive = false; clearInterval(iv); };
  }, []);

  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center gap-3 border-r border-line py-4">
        <button onClick={onToggle} title="Expand" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink">
          <PanelLeft size={18} />
        </button>
        <button onClick={onNew} title="New chat" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink">
          <Plus size={18} />
        </button>
        <span
          title={health === undefined ? "Connecting" : health ? "Connected" : "Offline"}
          className={`mt-auto h-1.5 w-1.5 rounded-full ${health === undefined ? "bg-warn" : health ? "bg-ok glow-pulse" : "bg-err"}`}
        />
        <button onClick={onOpenSettings} title="Settings" className="rounded-lg p-2 text-ink-faint hover:bg-surface-2 hover:text-ink">
          <Settings size={18} />
        </button>
      </div>
    );
  }

  const filtered = q ? items.filter((i) => i.title.toLowerCase().includes(q.toLowerCase())) : items;

  return (
    <div className="flex h-full flex-col border-r border-line">
      {/* header */}
      <div className="flex items-center justify-between px-3 pb-2 pt-4">
        <div className="wordmark flex items-center gap-2 px-1 text-[19px]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/searchos-mark.png" alt="" className="h-6 w-6 rounded-md dark:bg-white dark:p-0.5" />
          SearchOS
        </div>
        <button onClick={onToggle} title="Collapse" className="rounded-lg p-1.5 text-ink-faint hover:bg-surface-2 hover:text-ink">
          <PanelLeftClose size={17} />
        </button>
      </div>

      {/* new chat */}
      <div className="px-3 pb-2">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 py-2 text-[14px] font-medium text-ink transition-colors hover:bg-surface-2"
        >
          <Plus size={16} /> New chat
        </button>
      </div>

      {/* search */}
      <div className="px-3 pb-3">
        <label className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] text-ink-faint">
          <Search size={14} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search"
            className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
          />
        </label>
      </div>

      {/* list */}
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
        {filtered.length === 0 ? (
          <p className="px-2 pt-2 text-[12.5px] text-ink-faint">{items.length ? "No matches" : "No conversations yet"}</p>
        ) : (
          <>
            <div className="px-2 pb-1 pt-1 text-[11px] uppercase tracking-wider text-ink-faint">Recent</div>
            {filtered.map((it) => {
              if (editingId === it.id) {
                return (
                  <div key={it.id} className="px-1 py-1">
                    <input
                      autoFocus
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => commitRename(it.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename(it.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      className="w-full rounded-md border border-line-strong bg-surface px-2 py-1.5 text-[13.5px] text-ink outline-none focus:border-accent"
                    />
                  </div>
                );
              }
              return (
                <div
                  key={it.id}
                  onMouseLeave={() => { if (confirmId === it.id) setConfirmId(null); }}
                  className={`group relative flex items-center rounded-lg pr-1 transition-colors ${
                    it.id === activeId ? "bg-clay/60" : "hover:bg-surface-2"
                  }`}
                >
                  <button
                    onClick={() => onSelect(it.id)}
                    className={`flex min-w-0 flex-1 items-center gap-2 py-2 pl-2.5 text-left text-[13.5px] ${
                      it.id === activeId ? "text-ink" : "text-ink-dim group-hover:text-ink"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT[it.status] ?? "bg-ink-faint"}`} />
                    <span className="truncate">{it.title}</span>
                  </button>

                  {confirmId === it.id ? (
                    <span className="flex shrink-0 items-center gap-0.5 pl-1">
                      <button title="Confirm delete" onClick={() => { onDelete(it.id); setConfirmId(null); }}
                        className="rounded p-1 text-err hover:bg-err/10"><Check size={14} /></button>
                      <button title="Cancel" onClick={() => setConfirmId(null)}
                        className="rounded p-1 text-ink-faint hover:bg-surface-2 hover:text-ink"><X size={14} /></button>
                    </span>
                  ) : (
                    <span className="flex shrink-0 items-center gap-0.5 pl-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
                      <button title="Rename" onClick={() => { setEditingId(it.id); setEditValue(it.title); }}
                        className="rounded p-1 text-ink-faint hover:bg-surface-2 hover:text-ink"><Pencil size={13} /></button>
                      <button title="Delete" onClick={() => setConfirmId(it.id)}
                        className="rounded p-1 text-ink-faint hover:bg-surface-2 hover:text-err"><Trash2 size={13} /></button>
                    </span>
                  )}
                </div>
              );
            })}
          </>
        )}
      </div>

      {/* footer */}
      <div className="flex items-center justify-between border-t border-line px-4 py-3 text-[12px] text-ink-faint">
        <span className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${health === undefined ? "bg-warn" : health ? "bg-ok glow-pulse" : "bg-err"}`} />
          {health === undefined ? "Connecting" : health ? "Connected" : "Offline"}
        </span>
        <span className="flex items-center gap-0.5">
          <button onClick={onOpenSettings} title="Settings"
            className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
            <Settings size={16} />
          </button>
          <ThemeToggle />
        </span>
      </div>
    </div>
  );
}
