"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";

import { useSearch } from "@/hooks/useSearch";
import { getWorkspaceFiles, listHistory, loadHistory, renameHistory, deleteHistory, type HistoryItem } from "@/lib/api";
import { deriveAnswer, foldWorkers } from "@/lib/derive";
import type { FileNode, SearchRequest, SearchState, WSEvent } from "@/lib/types";
import type { Turn } from "@/lib/conversation";
import type { SubmitOpts } from "@/components/shell/Composer";

import HistoryRail from "@/components/shell/HistoryRail";
import Landing from "@/components/conversation/Landing";
import Conversation from "@/components/conversation/Conversation";
import ExecutionDrawer from "@/components/drawer/ExecutionDrawer";
import SettingsModal from "@/components/settings/SettingsModal";
import { useSettings } from "@/components/settings/SettingsProvider";

let turnSeq = 0;

export default function Home() {
  const { session, run, reset } = useSearch();
  const { overrides } = useSettings();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const [drawerTurnId, setDrawerTurnId] = useState<string | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  const refreshHistory = useCallback(() => {
    listHistory().then(setHistory).catch(() => {});
  }, []);
  useEffect(() => { refreshHistory(); }, [refreshHistory]);

  // Sync the live `session` into the active (running) turn.
  useEffect(() => {
    if (!activeTurnId) return;
    const searchState: SearchState | null = session.liveState || session.result?.search_state || null;
    const status: Turn["status"] =
      session.status === "completed" ? "completed" : session.status === "error" ? "error" : "running";

    setTurns((prev) =>
      prev.map((t) => {
        if (t.id !== activeTurnId) return t;
        return {
          ...t,
          sessionId: session.sessionId,
          status,
          events: session.events,
          workers: session.workers,
          searchState,
          answer: status === "completed" ? deriveAnswer(session.events) : t.answer,
          error: session.error,
          meta:
            status === "completed"
              ? {
                  coverageScore: session.result?.coverage_score,
                  evidenceCount: session.result?.evidence_count,
                  elapsed: session.result?.elapsed_s ?? session.elapsed,
                  verdict: session.result?.eval_verdict ?? null,
                }
              : t.meta,
        };
      }),
    );
  }, [session, activeTurnId]);

  // When a run finishes, the new workspace appears on disk — refresh history.
  useEffect(() => {
    if (session.status === "completed" || session.status === "error") refreshHistory();
  }, [session.status, refreshHistory]);

  // Fetch workspace files for whichever turn's drawer is open.
  const drawerTurn = turns.find((t) => t.id === drawerTurnId) ?? null;
  const drawerSession = drawerTurn?.sessionId ?? null;
  const drawerStatus = drawerTurn?.status;
  useEffect(() => {
    if (!drawerSession) return;
    const refresh = () => getWorkspaceFiles(drawerSession).then((r) => setFileTree(r.tree)).catch(() => {});
    refresh();
    if (drawerStatus === "running") {
      const id = setInterval(refresh, 3000);
      return () => clearInterval(id);
    }
  }, [drawerSession, drawerStatus]);

  const handleSubmit = useCallback(
    (q: string, opts: SubmitOpts) => {
      const id = `t${++turnSeq}`;
      const turn: Turn = {
        id, query: q, sessionId: null, status: "running",
        events: [], workers: [], searchState: null, answer: "", meta: {}, error: null,
      };
      setTurns((prev) => [...prev, turn]);
      setActiveTurnId(id);
      setSelectedFile(null);
      run({
        query: q,
        type: (opts.type as SearchRequest["type"]) || undefined,
        entities: opts.entities,
        attrs: opts.attrs,
        effort: overrides.effort,
        max_time: overrides.max_time,
      });
    },
    [run, overrides],
  );

  const handleNew = useCallback(() => {
    reset();
    setTurns([]);
    setActiveTurnId(null);
    setDrawerTurnId(null);
    setFileTree([]);
    setSelectedFile(null);
  }, [reset]);

  const turnRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Currently-open session id (live turn's sessionId or a loaded session id).
  const openTurn = turns[turns.length - 1] ?? null;
  const openId = openTurn ? openTurn.sessionId ?? openTurn.id : null;

  const handleSelect = useCallback(
    async (id: string) => {
      // Already open? just scroll to it.
      const existing = turns.find((t) => (t.sessionId ?? t.id) === id);
      if (existing) {
        turnRefs.current[existing.id]?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      try {
        const data = await loadHistory(id);
        const events: WSEvent[] = data.events ?? [];
        const turn: Turn = {
          id: data.session_id,
          query: data.query,
          sessionId: data.session_id,
          status: data.status === "running" ? "running" : "completed",
          events,
          workers: foldWorkers(events, data.status !== "running"),
          searchState: (data.search_state as SearchState) ?? null,
          answer: data.answer ?? "",
          meta: {
            coverageScore: data.coverage_score ?? undefined,
            evidenceCount: data.evidence_count ?? undefined,
          },
          error: null,
        };
        reset();
        setActiveTurnId(null);
        setDrawerTurnId(null);
        setSelectedFile(null);
        setTurns([turn]);
      } catch {
        /* ignore load failure */
      }
    },
    [turns, reset],
  );

  const handleRename = useCallback((id: string, title: string) => {
    setHistory((prev) => prev.map((h) => (h.session_id === id ? { ...h, title } : h)));
    setTurns((prev) => prev.map((t) => ((t.sessionId ?? t.id) === id ? { ...t, query: title } : t)));
    renameHistory(id, title).catch(() => {}).finally(refreshHistory);
  }, [refreshHistory]);

  const handleDelete = useCallback((id: string) => {
    setHistory((prev) => prev.filter((h) => h.session_id !== id));
    if (openId === id) handleNew();
    deleteHistory(id).catch(() => {}).finally(refreshHistory);
  }, [openId, handleNew, refreshHistory]);

  // Rail = disk history; prepend the live run if it isn't on disk yet.
  const railItems = useMemo(() => {
    const items = history.map((h) => ({
      id: h.session_id,
      title: h.title,
      status: (h.status === "incomplete" ? "completed" : h.status) as "running" | "completed" | "error",
    }));
    if (openTurn && openTurn.status === "running") {
      const sid = openTurn.sessionId ?? openTurn.id;
      if (!items.some((i) => i.id === sid)) items.unshift({ id: sid, title: openTurn.query, status: "running" });
    }
    return items;
  }, [history, openTurn]);

  const drawerOpen = !!drawerTurn;

  return (
    <div
      className="grid h-screen transition-[grid-template-columns] duration-300 ease-out"
      style={{
        gridTemplateColumns: `${railCollapsed ? "56px" : "264px"} minmax(0,1fr) ${drawerOpen ? "minmax(0,460px)" : "0px"}`,
      }}
    >
      <HistoryRail
        items={railItems}
        activeId={openId}
        collapsed={railCollapsed}
        onToggle={() => setRailCollapsed((v) => !v)}
        onNew={handleNew}
        onSelect={handleSelect}
        onRename={handleRename}
        onDelete={handleDelete}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="min-w-0 overflow-hidden">
        {turns.length === 0 ? (
          <Landing onSubmit={handleSubmit} error={session.error} />
        ) : (
          <Conversation
            turns={turns}
            running={session.status === "running"}
            onSubmit={handleSubmit}
            onOpenDrawer={setDrawerTurnId}
            registerTurnRef={(id, el) => { turnRefs.current[id] = el; }}
          />
        )}
      </main>

      <div className="min-w-0 overflow-hidden">
        {drawerTurn && (
          <ExecutionDrawer
            turn={drawerTurn}
            sessionId={drawerTurn.sessionId}
            fileTree={fileTree}
            selectedFile={selectedFile}
            onSelectFile={setSelectedFile}
            onClose={() => setDrawerTurnId(null)}
          />
        )}
      </div>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
