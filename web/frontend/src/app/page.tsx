"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";

import { useSearch } from "@/hooks/useSearch";
import { getWorkspaceFiles, listHistory, loadHistory, renameHistory, deleteHistory, steerSearch, stopSearch, type HistoryItem } from "@/lib/api";
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
  const { session, run, attach, reset } = useSearch();
  const { overrides, notify } = useSettings();
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
          // Prefer the durable full answer from the result fetch; the
          // event-stream preview (deriveAnswer) is truncated server-side.
          answer: status === "completed" ? session.result?.answer || deriveAnswer(session.events) : t.answer,
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
      // Follow-up (TUI parity): the previous turn finished in this session →
      // extend its workspace/coverage table and pass the conversation history.
      const prev = turns[turns.length - 1];
      const followUpTo =
        prev && prev.status === "completed" && prev.sessionId ? prev.sessionId : undefined;
      const history = followUpTo
        ? turns
            .filter((t) => t.status === "completed")
            .map((t) => ({ query: t.query, answer: t.answer }))
        : undefined;

      const id = `t${++turnSeq}`;
      const turn: Turn = {
        id, query: q, sessionId: null, status: "running",
        events: [], workers: [], searchState: null, answer: "", meta: {}, error: null,
      };
      setTurns((prevTurns) => [...prevTurns, turn]);
      setActiveTurnId(id);
      setSelectedFile(null);
      run({
        query: q,
        type: (opts.type as SearchRequest["type"]) || undefined,
        entities: opts.entities,
        attrs: opts.attrs,
        table_label: opts.tableLabel,
        primary_key: opts.primaryKey,
        row_label: opts.rowLabel,
        tables: opts.tables,
        relations: opts.relations,
        effort: overrides.effort,
        max_time: overrides.max_time,
        follow_up_to: followUpTo,
        history,
      });
    },
    [run, overrides, turns],
  );

  // Live follow-up: inject into the running orchestrator (sub-agents keep
  // running) instead of queueing a new search — same as the TUI mid-run path.
  const handleSteer = useCallback(
    (text: string) => {
      const sid = session.sessionId;
      if (!sid || session.status !== "running") {
        notify("Run not ready yet — try again in a moment");
        return;
      }
      const turnId = activeTurnId;
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId ? { ...t, followUps: [...(t.followUps ?? []), text] } : t,
        ),
      );
      steerSearch(sid, text).catch((e) => {
        // Roll the echo back and say why — a silent disappearance reads as
        // "steering doesn't work".
        notify(`Steer failed: ${e instanceof Error ? e.message : String(e)}`);
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? { ...t, followUps: (t.followUps ?? []).filter((f) => f !== text) }
              : t,
          ),
        );
      });
    },
    [session.sessionId, session.status, activeTurnId, notify],
  );

  // Interrupt the live run (TUI Esc parity). The backend cancels the engine
  // task; the WS then delivers the terminal event and the turn settles.
  const handleStop = useCallback(() => {
    const sid = session.sessionId;
    if (!sid || session.status !== "running") return;
    stopSearch(sid).catch(() => {});
  }, [session.sessionId, session.status]);

  const handleNew = useCallback(() => {
    reset();
    setTurns([]);
    setActiveTurnId(null);
    setDrawerTurnId(null);
    setFileTree([]);
    setSelectedFile(null);
    // A live run we just walked away from keeps running server-side — make
    // sure it shows up in the rail (as running) so the user can switch back.
    refreshHistory();
  }, [reset, refreshHistory]);

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
        const isRunning = data.status === "running";
        // Restore the full dialogue: one Turn per reconstructed turn. Each
        // run appends a `task_start` trajectory event, so the flat event log
        // splits into per-turn segments — every restored turn gets its own
        // orchestration trace, same as a live run. Segments tail-align to
        // turns (surplus leading segments fold into the first turn).
        const hist: { query: string; answer: string; steers?: string[] }[] =
          data.turns?.length ? data.turns : [{ query: data.query, answer: data.answer ?? "" }];
        const segments: WSEvent[][] = [];
        for (const e of events) {
          const d = (e.data ?? {}) as Record<string, unknown>;
          const isBoundary = e.type === "trajectory" && d.type === "task_start";
          if (isBoundary || segments.length === 0) segments.push([]);
          segments[segments.length - 1].push(e);
        }
        const last = hist.length - 1;
        const segFor = (i: number): WSEvent[] => {
          const idx = segments.length - (hist.length - i);
          if (idx < 0) return [];
          if (i === 0) return segments.slice(0, idx + 1).flat();
          return segments[idx] ?? [];
        };
        const restored: Turn[] = hist.map((h, i) => {
          const segEvents = segFor(i);
          const turnRunning = i === last && isRunning;
          return {
            id: i === last ? data.session_id : `${data.session_id}#${i}`,
            query: h.query || data.query,
            sessionId: data.session_id,
            status: turnRunning ? "running" as const : "completed" as const,
            events: segEvents,
            workers: foldWorkers(segEvents, !turnRunning),
            searchState: i === last ? ((data.search_state as SearchState) ?? null) : null,
            answer: i === last ? (data.answer || h.answer || "") : h.answer,
            followUps: h.steers?.length ? h.steers : undefined,
            meta: i === last
              ? {
                  coverageScore: data.coverage_score ?? undefined,
                  evidenceCount: data.evidence_count ?? undefined,
                }
              : {},
            error: null,
          };
        });
        const turn = restored[last];
        setDrawerTurnId(null);
        setSelectedFile(null);
        setTurns(restored);
        // If we just walked away from a live run, it keeps running server-side
        // — refresh so the rail lists it (as running) for switching back.
        refreshHistory();
        if (isRunning) {
          // The backend still owns this run — re-attach the live WS/steer
          // channel so events keep streaming and follow-ups can be injected.
          // Seed only the live turn's segment; dedupe against the full log.
          setActiveTurnId(turn.id);
          attach(data.session_id, { events: turn.events, searchState: turn.searchState, seen: events });
        } else {
          reset();
          setActiveTurnId(null);
        }
      } catch {
        /* ignore load failure */
      }
    },
    [turns, reset, attach, refreshHistory],
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
            onSteer={handleSteer}
            onStop={handleStop}
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
