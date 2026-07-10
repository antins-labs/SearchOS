"use client";

import { useState, useEffect, useCallback, useRef, useMemo, type CSSProperties } from "react";
import { Menu } from "lucide-react";

import { useSearch } from "@/hooks/useSearch";
import { branchHistoryTurn, getWorkspaceFiles, listHistory, loadHistory, renameHistory, deleteHistory, resolveEvidence, steerSearch, stopSearch, type HistoryItem, type HistoryTurn } from "@/lib/api";
import { deriveAnswer, foldWorkers } from "@/lib/derive";
import type { FileNode, RepairCellTarget, SearchRequest, SearchState, WSEvent } from "@/lib/types";
import type { Turn } from "@/lib/conversation";
import type { SubmitOpts } from "@/components/shell/Composer";

import HistoryRail from "@/components/shell/HistoryRail";
import Landing from "@/components/conversation/Landing";
import Conversation from "@/components/conversation/Conversation";
import ExecutionDrawer from "@/components/drawer/ExecutionDrawer";
import SettingsModal from "@/components/settings/SettingsModal";
import { useSettings } from "@/components/settings/SettingsProvider";
import {
  MAX_ACTIVITY_WIDTH,
  MIN_ACTIVITY_WIDTH,
  updateActivityPreferences,
  useActivityPreferences,
} from "@/lib/activityPreferences";

let turnSeq = 0;

export default function Home() {
  const { session, run, repair, attach, reset } = useSearch();
  const { overrides, notify } = useSettings();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const [drawerTurnId, setDrawerTurnId] = useState<string | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [drawerResizing, setDrawerResizing] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyStatus, setHistoryStatus] = useState<"loading" | "ready" | "error">("loading");
  const [historyLoadingId, setHistoryLoadingId] = useState<string | null>(null);
  const [historyMutation, setHistoryMutation] = useState<{ id: string; kind: "rename" | "delete" } | null>(null);
  const [stopPending, setStopPending] = useState(false);
  const [branchingTurnId, setBranchingTurnId] = useState<string | null>(null);
  const [composerFocusRequest, setComposerFocusRequest] = useState(0);
  const historyBusyRef = useRef(false);
  const stopPendingRef = useRef(false);

  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileStatus, setFileStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileRetrySeq, setFileRetrySeq] = useState(0);
  const sessionActive = session.status === "running" || session.status === "reconnecting";
  const activityPreferences = useActivityPreferences();

  useEffect(() => {
    const root = document.documentElement;
    const phase = session.status === "running" || session.status === "reconnecting"
      ? "running"
      : session.status === "completed"
        ? "completed"
        : session.status === "error"
          ? "error"
          : "idle";
    root.dataset.maxPhase = phase;
    return () => {
      delete root.dataset.maxPhase;
    };
  }, [session.status]);

  const refreshHistory = useCallback(async (announceFailure = false) => {
    try {
      setHistory(await listHistory());
      setHistoryStatus("ready");
    } catch (e) {
      setHistoryStatus("error");
      if (announceFailure) {
        notify(`Couldn’t refresh history: ${e instanceof Error ? e.message : String(e)}. Check the backend and try again.`);
      }
    }
  }, [notify]);
  useEffect(() => { void refreshHistory(); }, [refreshHistory]);

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
                  totalQueries: session.result?.total_queries,
                  totalSteps: session.result?.total_steps,
                  toolCounts: session.result?.tool_counts,
                  tokenUsage: session.result?.token_usage,
                  tokenPhases: session.result?.token_phases,
                  modelDistribution: session.result?.model_distribution,
                }
              : { ...t.meta, elapsed: session.elapsed },
        };
      }),
    );
  }, [session, activeTurnId]);

  // When a run finishes, the new workspace appears on disk — refresh history.
  useEffect(() => {
    if (session.status === "completed" || session.status === "error") void refreshHistory();
  }, [session.status, refreshHistory]);

  // Fetch workspace files for whichever turn's drawer is open.
  const drawerTurn = turns.find((t) => t.id === drawerTurnId) ?? null;
  const drawerSession = drawerTurn?.sessionId ?? null;
  const drawerStatus = drawerTurn?.status;
  useEffect(() => {
    if (!drawerSession) return;
    let alive = true;
    let inFlight = false;
    const refresh = () => {
      if (inFlight) return;
      inFlight = true;
      void getWorkspaceFiles(drawerSession)
      .then((r) => {
        if (!alive) return;
        setFileTree(r.tree);
        setFileStatus("ready");
        setFileError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setFileStatus("error");
        setFileError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => { inFlight = false; });
    };
    refresh();
    if (drawerStatus === "running") {
      const id = setInterval(refresh, 3000);
      return () => { alive = false; clearInterval(id); };
    }
    return () => { alive = false; };
  }, [drawerSession, drawerStatus, fileRetrySeq]);

  const handleSubmit = useCallback(
    (q: string, opts: SubmitOpts, freshRun = false) => {
      stopPendingRef.current = false;
      setStopPending(false);
      // Follow-up (TUI parity): the previous turn finished in this session →
      // extend its workspace/coverage table and pass the conversation history.
      const prev = freshRun ? undefined : turns[turns.length - 1];
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
        events: [], workers: [], searchState: null, stateSource: "live", answer: "", meta: {}, error: null,
      };
      setTurns((prevTurns) => freshRun ? [turn] : [...prevTurns, turn]);
      setActiveTurnId(id);
      setSelectedFile(null);
      if (freshRun) {
        setDrawerTurnId(null);
        setFileTree([]);
        setFileStatus("idle");
        setFileError(null);
      }
      run(
        {
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
        },
        { seen: followUpTo ? turns.flatMap((item) => item.events) : undefined },
      );
    },
    [run, overrides, turns],
  );

  const handleRerun = useCallback((query: string) => {
    handleSubmit(query, {}, true);
  }, [handleSubmit]);

  const handleRepair = useCallback((sourceTurn: Turn, cells: RepairCellTarget[]) => {
    if (sessionActive || !sourceTurn.sessionId || !sourceTurn.searchState || cells.length === 0) return;
    const snapshots = cells.flatMap((cell) => {
      const key = `${cell.table_id}/${cell.entity}.${cell.attribute}`;
      const before = sourceTurn.searchState?.coverage_map.cells[key];
      return before ? [{ ...cell, before: { status: before.status, value: before.value } }] : [];
    });
    if (snapshots.length === 0) {
      notify("Those cells are no longer available. Refresh the result and try again.");
      return;
    }

    stopPendingRef.current = false;
    setStopPending(false);
    const id = `t${++turnSeq}`;
    const count = snapshots.length;
    const turn: Turn = {
      id,
      query: `Repair ${count} selected ${count === 1 ? "cell" : "cells"}`,
      sessionId: sourceTurn.sessionId,
      status: "running",
      events: [],
      workers: [],
      searchState: sourceTurn.searchState,
      stateSource: "live",
      answer: "",
      repair: {
        cells: snapshots,
        evidenceIdsBefore: sourceTurn.searchState.evidence_graph.nodes.map((node) => node.id),
      },
      meta: {},
      error: null,
    };
    setTurns((current) => [...current, turn]);
    setActiveTurnId(id);
    setSelectedFile(null);
    if (drawerTurnId === sourceTurn.id) setDrawerTurnId(id);

    const history = turns
      .filter((item) => item.status === "completed")
      .map((item) => ({ query: item.query, answer: item.answer }));
    void repair(
      sourceTurn.sessionId,
      {
        cells: snapshots.map(({ table_id, entity, attribute }) => ({ table_id, entity, attribute })),
        effort: overrides.effort,
        max_time: overrides.max_time,
        history,
      },
      {
        seen: turns.flatMap((item) => item.events),
        initialState: sourceTurn.searchState,
        onStarted: (response) => {
          setTurns((current) => current.map((item) => item.id === id && item.repair
            ? {
                ...item,
                repair: {
                  ...item.repair,
                  planner: response.planner,
                  planningLatencyMs: response.planning_latency_ms,
                  planningWarning: response.planning_warning,
                },
              }
            : item));
          if (response.planning_warning) notify(response.planning_warning, "info");
        },
      },
    ).then((startError) => {
      if (!startError) return;
      setTurns((current) => current.filter((item) => item.id !== id));
      setActiveTurnId(null);
      if (drawerTurnId === sourceTurn.id) setDrawerTurnId(sourceTurn.id);
      reset();
      notify(startError);
    });
  }, [drawerTurnId, notify, overrides, repair, reset, sessionActive, turns]);

  const handleResolveEvidence = useCallback(async (
    sourceTurn: Turn,
    target: RepairCellTarget,
    evidenceId: string,
  ) => {
    if (sessionActive || !sourceTurn.sessionId) {
      throw new Error("This result cannot be edited while research is running");
    }
    try {
      const response = await resolveEvidence(sourceTurn.sessionId, {
        ...target,
        evidence_id: evidenceId,
      });
      setTurns((current) => current.map((turn) => turn.id === sourceTurn.id
        ? {
            ...turn,
            searchState: response.search_state,
            meta: { ...turn.meta, evidenceCount: response.search_state.evidence_graph.nodes.length },
          }
        : turn));
      notify("Evidence choice applied", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      notify(`Couldn’t apply this source: ${message}`);
      throw error;
    }
  }, [notify, sessionActive]);

  // Live follow-up: inject into the running orchestrator (sub-agents keep
  // running) instead of queueing a new search — same as the TUI mid-run path.
  const handleSteer = useCallback(
    (text: string) => {
      const sid = session.sessionId;
      if (!sid || (session.status !== "running" && session.status !== "reconnecting")) {
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
  const handleStop = useCallback(async () => {
    const sid = session.sessionId;
    if (!sid || (session.status !== "running" && session.status !== "reconnecting") || stopPendingRef.current) return;
    stopPendingRef.current = true;
    setStopPending(true);
    try {
      await stopSearch(sid);
      notify("Stop requested. Waiting for the current run to finish shutting down.", "info");
    } catch (e) {
      stopPendingRef.current = false;
      setStopPending(false);
      notify(`Couldn’t stop this run: ${e instanceof Error ? e.message : String(e)}. Try again.`);
    }
  }, [session.sessionId, session.status, notify]);

  const handleNew = useCallback(() => {
    reset();
    setTurns([]);
    setActiveTurnId(null);
    setDrawerTurnId(null);
    setFileTree([]);
    setFileStatus("idle");
    setFileError(null);
    setSelectedFile(null);
    stopPendingRef.current = false;
    setStopPending(false);
    // A live run we just walked away from keeps running server-side — make
    // sure it shows up in the rail (as running) so the user can switch back.
    void refreshHistory();
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
      if (historyBusyRef.current) return;
      historyBusyRef.current = true;
      setHistoryLoadingId(id);
      try {
        const data = await loadHistory(id);
        const events: WSEvent[] = data.events ?? [];
        const isRunning = data.status === "running";
        // Restore the full dialogue: one Turn per reconstructed turn. Each
        // run appends a `task_start` trajectory event, so the flat event log
        // splits into per-turn segments — every restored turn gets its own
        // orchestration trace, same as a live run. Segments tail-align to
        // turns (surplus leading segments fold into the first turn).
        const hist: HistoryTurn[] = data.turns.length ? data.turns : [{
          query: data.query,
          answer: data.answer ?? "",
          search_state: data.search_state,
          state_source: data.search_state ? "latest" : "unavailable",
          coverage_score: data.coverage_score,
          evidence_count: data.evidence_count,
        }];
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
            searchState: h.search_state,
            stateSource: turnRunning ? "live" : h.state_source,
            answer: h.answer || (i === last ? data.answer : ""),
            followUps: h.steers?.length ? h.steers : undefined,
            meta: {
              coverageScore: h.coverage_score ?? undefined,
              evidenceCount: h.evidence_count ?? undefined,
              elapsed: h.elapsed_s ?? undefined,
              totalQueries: h.total_queries ?? undefined,
              totalSteps: h.total_steps ?? undefined,
              toolCounts: h.tool_counts ?? undefined,
              tokenUsage: h.token_usage ?? undefined,
              tokenPhases: h.token_phases ?? undefined,
              modelDistribution: h.model_distribution ?? undefined,
            },
            error: null,
          };
        });
        const turn = restored[last];
        setDrawerTurnId(null);
        setSelectedFile(null);
        setTurns(restored);
        // If we just walked away from a live run, it keeps running server-side
        // — refresh so the rail lists it (as running) for switching back.
        void refreshHistory();
        if (isRunning) {
          // The backend still owns this run — re-attach the live WS/steer
          // channel so events keep streaming and follow-ups can be injected.
          // Seed only the live turn's segment; dedupe against the full log.
          stopPendingRef.current = false;
          setStopPending(false);
          setActiveTurnId(turn.id);
          attach(data.session_id, { events: turn.events, searchState: turn.searchState, seen: events });
        } else {
          reset();
          setActiveTurnId(null);
        }
      } catch (e) {
        const title = history.find((item) => item.session_id === id)?.title ?? "this conversation";
        notify(`Couldn’t open ${title}: ${e instanceof Error ? e.message : String(e)}. Refresh history and try again.`);
      } finally {
        historyBusyRef.current = false;
        setHistoryLoadingId(null);
      }
    },
    [turns, reset, attach, refreshHistory, history, notify],
  );

  const handleBranchTurn = useCallback(async (turnId: string, focusComposer: boolean) => {
    if (sessionActive || branchingTurnId) return;
    const turnIndex = turns.findIndex((turn) => turn.id === turnId);
    const source = turns[turnIndex];
    if (turnIndex < 0 || !source?.sessionId || !source.searchState) {
      notify("This version has no restorable snapshot.");
      return;
    }

    setBranchingTurnId(turnId);
    try {
      const branch = await branchHistoryTurn(source.sessionId, turnIndex);
      await handleSelect(branch.session_id);
      if (focusComposer) setComposerFocusRequest((value) => value + 1);
      notify(
        focusComposer
          ? `Branch created from V${turnIndex + 1}. Continue your research below.`
          : `V${turnIndex + 1} copied as a new conversation.`,
        "success",
      );
      void refreshHistory();
    } catch (error) {
      notify(`Couldn’t create this version branch: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBranchingTurnId(null);
    }
  }, [branchingTurnId, handleSelect, notify, refreshHistory, sessionActive, turns]);

  const handleRename = useCallback(async (id: string, title: string) => {
    if (historyBusyRef.current) return;
    historyBusyRef.current = true;
    setHistoryMutation({ id, kind: "rename" });
    try {
      await renameHistory(id, title);
      setHistory((prev) => prev.map((h) => (h.session_id === id ? { ...h, title } : h)));
      setTurns((prev) => prev.map((t) => ((t.sessionId ?? t.id) === id ? { ...t, query: title } : t)));
      notify("Conversation renamed", "success");
      void refreshHistory();
    } catch (e) {
      notify(`Couldn’t rename this conversation: ${e instanceof Error ? e.message : String(e)}. Your previous title was kept.`);
    } finally {
      historyBusyRef.current = false;
      setHistoryMutation(null);
    }
  }, [refreshHistory, notify]);

  const handleDelete = useCallback(async (id: string) => {
    if (historyBusyRef.current) return;
    historyBusyRef.current = true;
    setHistoryMutation({ id, kind: "delete" });
    try {
      await deleteHistory(id);
      setHistory((prev) => prev.filter((h) => h.session_id !== id));
      if (openId === id) handleNew();
      notify("Conversation deleted", "success");
      void refreshHistory();
    } catch (e) {
      notify(`Couldn’t delete this conversation: ${e instanceof Error ? e.message : String(e)}. Nothing was removed.`);
    } finally {
      historyBusyRef.current = false;
      setHistoryMutation(null);
    }
  }, [openId, handleNew, refreshHistory, notify]);

  const handleOpenDrawer = useCallback((turnId: string) => {
    const target = turns.find((turn) => turn.id === turnId);
    setDrawerTurnId(turnId);
    setSelectedFile(null);
    setFileTree([]);
    setFileError(null);
    setFileStatus(target?.sessionId ? "loading" : "idle");
  }, [turns]);

  const handleRetryHistory = useCallback(() => {
    if (historyStatus === "loading") return;
    setHistoryStatus("loading");
    void refreshHistory(true);
  }, [historyStatus, refreshHistory]);

  const handleRetryFiles = useCallback(() => {
    if (!drawerSession || fileStatus === "loading") return;
    setFileStatus("loading");
    setFileError(null);
    setFileRetrySeq((value) => value + 1);
  }, [drawerSession, fileStatus]);

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
  const latestEditableTurn = [...turns].reverse().find((turn) => (
    turn.status === "completed" && !!turn.sessionId && !!turn.searchState
  ));
  const drawerEditable = !sessionActive && latestEditableTurn?.id === drawerTurn?.id;

  return (
    <div
      className={`grid h-[100dvh] grid-cols-[minmax(0,1fr)] min-[1180px]:grid-cols-[var(--rail-width)_minmax(0,1fr)_var(--drawer-width)] ${drawerResizing ? "" : "transition-[grid-template-columns] duration-300 ease-out"}`}
      style={{
        "--rail-width": railCollapsed ? "56px" : "264px",
        "--drawer-width": drawerOpen
          ? `clamp(${MIN_ACTIVITY_WIDTH}px, ${activityPreferences.width}px, min(${MAX_ACTIVITY_WIDTH}px, calc(100vw - var(--rail-width) - 420px)))`
          : "0px",
      } as CSSProperties}
    >
      {mobileRailOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileRailOpen(false)}
          className="fade-in fixed inset-0 z-40 bg-ink/20 min-[1180px]:hidden dark:bg-black/50"
        />
      )}

      <aside
        className={`${
          mobileRailOpen
            ? "fixed inset-y-0 left-0 z-50 block w-[min(320px,88vw)] bg-paper shadow-2xl"
            : "hidden"
        } min-[1180px]:static min-[1180px]:z-auto min-[1180px]:block min-[1180px]:w-auto min-[1180px]:shadow-none`}
      >
        <HistoryRail
          items={railItems}
          activeId={openId}
          collapsed={mobileRailOpen ? false : railCollapsed}
          onToggle={() => mobileRailOpen ? setMobileRailOpen(false) : setRailCollapsed((v) => !v)}
          onNew={() => { setMobileRailOpen(false); handleNew(); }}
          onSelect={(id) => { setMobileRailOpen(false); void handleSelect(id); }}
          onRename={(id, title) => { void handleRename(id, title); }}
          onDelete={(id) => { void handleDelete(id); }}
          onOpenSettings={() => { setMobileRailOpen(false); setSettingsOpen(true); }}
          loadingId={historyLoadingId}
          mutation={historyMutation}
          historyStatus={historyStatus}
          onRetryHistory={handleRetryHistory}
        />
      </aside>

      <main className="relative min-w-0 overflow-hidden">
        <div className="fixed inset-x-0 top-0 z-30 flex h-12 items-center gap-2 border-b border-line bg-paper/95 px-3 backdrop-blur-sm min-[1180px]:hidden">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileRailOpen(true)}
            className="rounded-lg p-2 text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <Menu size={18} />
          </button>
          <span className="wordmark text-[16px]">SearchOS</span>
        </div>
        {turns.length === 0 ? (
          <Landing onSubmit={handleSubmit} error={session.error} />
        ) : (
          <Conversation
            turns={turns}
            running={sessionActive}
            reconnecting={session.status === "reconnecting"}
            stopping={stopPending}
            onSubmit={handleSubmit}
            onSteer={handleSteer}
            onStop={handleStop}
            onRerun={handleRerun}
            onRepair={handleRepair}
            onOpenDrawer={handleOpenDrawer}
            focusRequest={composerFocusRequest}
            registerTurnRef={(id, el) => { turnRefs.current[id] = el; }}
          />
        )}
      </main>

      <div className={`${drawerTurn ? "fixed inset-0 z-40" : "hidden"} min-w-0 overflow-hidden min-[1180px]:static min-[1180px]:z-auto min-[1180px]:block`}>
        {drawerTurn && (
          <ExecutionDrawer
            turn={drawerTurn}
            turns={turns}
            sessionId={drawerTurn.sessionId}
            fileTree={fileTree}
            selectedFile={selectedFile}
            onSelectFile={setSelectedFile}
            fileStatus={fileStatus}
            fileError={fileError}
            onRetryFiles={handleRetryFiles}
            onClose={() => setDrawerTurnId(null)}
            tab={activityPreferences.tab}
            onTabChange={(tab) => updateActivityPreferences({ tab })}
            width={activityPreferences.width}
            railWidth={railCollapsed ? 56 : 264}
            onWidthChange={(width) => updateActivityPreferences({ width }, false)}
            onWidthCommit={(width) => updateActivityPreferences({ width })}
            onResizeStateChange={setDrawerResizing}
            onRepairCells={
              drawerEditable
                ? (cells) => handleRepair(drawerTurn, cells)
                : undefined
            }
            onResolveEvidence={drawerEditable
              ? (target, evidenceId) => handleResolveEvidence(drawerTurn, target, evidenceId)
              : undefined}
            onReverifyEvidence={drawerEditable
              ? (target) => handleRepair(drawerTurn, [target])
              : undefined}
            onBranchTurn={sessionActive ? undefined : handleBranchTurn}
            branchingTurnId={branchingTurnId}
            subagentsCollapsed={activityPreferences.subagentsCollapsed}
            onSubagentsCollapsedChange={(subagentsCollapsed) => updateActivityPreferences({ subagentsCollapsed })}
          />
        )}
      </div>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
