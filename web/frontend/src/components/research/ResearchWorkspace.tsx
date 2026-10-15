"use client";

import { useState, useEffect, useCallback, useRef, useMemo, type CSSProperties } from "react";
import { Activity, Database, History, Menu, MessageSquare, Plus, Settings2, X } from "lucide-react";
import useDialogFocus from "@/hooks/useDialogFocus";

import { useSearch } from "@/hooks/useSearch";
import { useLocalLibrary } from "@/hooks/useLocalLibrary";
import { branchHistoryTurn, getWorkspaceFiles, listHistory, loadHistory, updateHistoryAssets, deleteHistory, resolveEvidence, steerSearch, stopSearch, type HistoryAssetPatch, type HistoryItem, type HistoryTurn } from "@/lib/api";
import { deriveAnswer, foldWorkers } from "@/lib/derive";
import type { FileNode, RepairCellTarget, SearchState, WSEvent } from "@/lib/types";
import {
  continuationSessionId,
  historyEventSegments,
  restoredRunState,
  type Turn,
} from "@/lib/conversation";
import type { SubmitOpts } from "@/components/shell/Composer";

import MobileAssistant from "@/components/mobile/MobileAssistant";
import HistoryRail from "@/components/shell/HistoryRail";
import KnowledgeBasePanel from "@/components/local/KnowledgeBasePanel";
import Landing from "@/components/conversation/Landing";
import Conversation from "@/components/conversation/Conversation";
import ExecutionDrawer from "@/components/drawer/ExecutionDrawer";
import SourcePanel from "@/components/sources/SourcePanel";
import SettingsModal from "@/components/settings/SettingsModal";
import { useSettings } from "@/components/settings/SettingsProvider";
import {
  MAX_ACTIVITY_WIDTH,
  MIN_ACTIVITY_WIDTH,
  updateActivityPreferences,
  useActivityPreferences,
} from "@/lib/activityPreferences";

let turnSeq = 0;

export default function ResearchWorkspace({ mobile = false }: { mobile?: boolean }) {
  const { session, run, repair, attach, reset } = useSearch();
  const localLibrary = useLocalLibrary();
  const restoreSourceSelection = localLibrary.restoreSelection;
  const { overrides, notify, status: backendStatus, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const [drawerTurnId, setDrawerTurnId] = useState<string | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [knowledgeBaseOpen, setKnowledgeBaseOpen] = useState(false);
  const [drawerResizing, setDrawerResizing] = useState(false);
  const [mobileAgentsCollapsed, setMobileAgentsCollapsed] = useState(true);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historySearchResults, setHistorySearchResults] = useState<HistoryItem[] | null>(null);
  const [historySearching, setHistorySearching] = useState(false);
  const [historyStatus, setHistoryStatus] = useState<"loading" | "ready" | "error">("loading");
  const [historyLoadingId, setHistoryLoadingId] = useState<string | null>(null);
  const [historyMutation, setHistoryMutation] = useState<{ id: string; kind: "delete" | "update" } | null>(null);
  const [stopPending, setStopPending] = useState(false);
  const [branchingTurnId, setBranchingTurnId] = useState<string | null>(null);
  const [composerFocusRequest, setComposerFocusRequest] = useState(0);
  const [localSourceRef, setLocalSourceRef] = useState<string | null>(null);
  const historyBusyRef = useRef(false);
  const stopPendingRef = useRef(false);
  const mobileRailTriggerRef = useRef<HTMLButtonElement>(null);
  const mobileRailRef = useRef<HTMLElement>(null);
  const mobileRailCloseRef = useRef<HTMLButtonElement>(null);

  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileStatus, setFileStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileRetrySeq, setFileRetrySeq] = useState(0);
  const sessionActive = session.status === "running" || session.status === "reconnecting";
  const activityPreferences = useActivityPreferences();

  const closeMobileRail = useCallback(() => {
    setMobileRailOpen(false);
    window.requestAnimationFrame(() => mobileRailTriggerRef.current?.focus());
  }, []);

  useDialogFocus({
    containerRef: mobileRailRef,
    initialFocusRef: mobileRailCloseRef,
    active: mobileRailOpen,
    onClose: closeMobileRail,
  });

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

  useEffect(() => {
    const query = historyQuery.trim();
    if (!query) {
      setHistorySearchResults(null);
      setHistorySearching(false);
      return;
    }
    let alive = true;
    setHistorySearching(true);
    const timer = window.setTimeout(() => {
      void listHistory(query)
        .then((items) => { if (alive) setHistorySearchResults(items); })
        .catch((error) => {
          if (alive) notify(`Couldn’t search research history: ${error instanceof Error ? error.message : String(error)}`);
        })
        .finally(() => { if (alive) setHistorySearching(false); });
    }, 250);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [historyQuery, notify]);

  // Sync the live `session` into the active (running) turn.
  useEffect(() => {
    if (!activeTurnId) return;
    const searchState: SearchState | null = session.liveState || session.result?.search_state || null;
    const status: Turn["status"] =
      session.status === "completed" ? "completed" : session.status === "error" ? "error" : "running";

    setTurns((prev) =>
      prev.map((t) => {
        if (t.id !== activeTurnId) return t;
        const liveAnswer = session.liveAnswer;
        return {
          ...t,
          sessionId: session.sessionId,
          status,
          events: session.events,
          workers: session.workers,
          searchState,
          // Prefer the durable result, including an intentional empty answer.
          // Fall back to trajectory-derived text only when no result exists.
          answer: status === "completed"
            ? session.result?.answer ?? deriveAnswer(session.events)
            : liveAnswer ?? t.answer,
          error: session.error,
          meta:
            status === "completed"
              ? {
                  coverageScore: session.result?.coverage_score ?? undefined,
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
              : { ...t.meta, elapsed: session.elapsed, startedAt: session.startedAt },
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
      // Keep the conversation across modes. The server fixes each turn's
      // source scope and resets prior evidence whenever that scope changes.
      const localRun = opts.sources?.mode === "local";
      const sourceMode = opts.sources?.mode ?? "web";
      const followUpTo = continuationSessionId(turns, sourceMode, freshRun);
      const sessionTurns = followUpTo
        ? turns
            .filter((t) => t.status === "completed" && t.sessionId === followUpTo)
        : [];
      const history = followUpTo
        ? sessionTurns
            .map((t) => ({ query: t.query, answer: t.answer }))
        : undefined;

      const id = `t${++turnSeq}`;
      const turn: Turn = {
        id, query: q, sessionId: null, status: "running",
        events: [], workers: [], searchState: null, stateSource: "live",
        sourceMode, answer: "", meta: {}, error: null,
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
          entities: opts.entities,
          attrs: opts.attrs,
          table_label: opts.tableLabel,
          primary_key: opts.primaryKey,
          row_label: opts.rowLabel,
          tables: opts.tables,
          relations: opts.relations,
          effort: overrides.effort,
          max_time: overrides.max_time,
          skills: overrides.skills,
          trusted_domains: localRun ? [] : overrides.trusted_domains,
          excluded_domains: localRun ? [] : overrides.excluded_domains,
          sources: opts.sources,
          follow_up_to: followUpTo,
          history,
        },
        { seen: followUpTo ? sessionTurns.flatMap((item) => item.events) : undefined },
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
        skills: overrides.skills,
        trusted_domains: overrides.trusted_domains,
        excluded_domains: overrides.excluded_domains,
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
        return Promise.resolve(false);
      }
      const turnId = activeTurnId;
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId ? { ...t, followUps: [...(t.followUps ?? []), text] } : t,
        ),
      );
      return steerSearch(sid, text).then(() => true).catch((e) => {
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
        return false;
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
        return true;
      }
      if (historyBusyRef.current) return false;
      historyBusyRef.current = true;
      setHistoryLoadingId(id);
      try {
        const data = await loadHistory(id);
        const events: WSEvent[] = data.events ?? [];
        const isRunning = data.status === "running";
        // Restore the full dialogue: one Turn per reconstructed turn. Each
        // run appends a `task_start` trajectory event, so the flat event log
        // splits into per-turn segments. Only segments that reached
        // `task_complete` align with completed dialogue turns; interrupted
        // runs must not shift another version's orchestration trace.
        const hist: HistoryTurn[] = data.turns.length ? data.turns : [{
          query: data.query,
          answer: data.answer ?? "",
          search_state: data.search_state,
          state_source: data.search_state ? "latest" : "unavailable",
          coverage_score: data.coverage_score,
          evidence_count: data.evidence_count,
        }];
        const segments = historyEventSegments(events, hist.length);
        const last = hist.length - 1;
        const restored: Turn[] = hist.map((h, i) => {
          const segEvents = segments[i] ?? [];
          const turnRunning = i === last && isRunning;
          const runState = restoredRunState(i === last ? data.status : "completed");
          return {
            id: i === last ? data.session_id : `${data.session_id}#${i}`,
            query: h.query || data.query,
            sessionId: data.session_id,
            status: runState.status,
            events: segEvents,
            workers: foldWorkers(segEvents, !turnRunning, runState.status === "error" ? "error" : "completed"),
            searchState: h.search_state,
            stateSource: turnRunning ? "live" : h.state_source,
            sourceMode: h.search_state?.source_scope?.mode ?? (segEvents.some((event) => (
              event.type === "trajectory"
              && (event.data as Record<string, unknown> | undefined)?.source_mode === "local"
            )) ? "local" : segEvents.some((event) => (
              event.type === "trajectory"
              && (event.data as Record<string, unknown> | undefined)?.source_mode === "hybrid"
            )) ? "hybrid" : "web"),
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
            error: runState.error,
          };
        });
        const turn = restored[last];
        const scope = turn.searchState?.source_scope;
        const restoredMode = scope?.mode ?? turn.sourceMode ?? "web";
        const documentIds = scope?.document_ids ?? scope?.documents.map((document) => document.document_id) ?? [];
        const restoredSelection = scope?.selection ?? (documentIds.length > 0 ? "documents" : "library");
        restoreSourceSelection({
          mode: restoredMode,
          ...(restoredMode !== "web" && scope?.library_id
              && (restoredMode === "local" || documentIds.length > 0) ? {
            local: { library_id: scope.library_id,
              document_ids: restoredSelection === "documents" ? documentIds : [],
              selection: restoredSelection, model_access: true as const },
          } : {}),
        });
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
        return true;
      } catch (e) {
        const title = history.find((item) => item.session_id === id)?.title ?? "this conversation";
        notify(`Couldn’t open ${title}: ${e instanceof Error ? e.message : String(e)}. Refresh history and try again.`);
        return false;
      } finally {
        historyBusyRef.current = false;
        setHistoryLoadingId(null);
      }
    },
    [turns, reset, attach, refreshHistory, history, notify, restoreSourceSelection],
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

  const handleUpdateHistoryAssets = useCallback(async (id: string, patch: HistoryAssetPatch) => {
    if (historyBusyRef.current) return;
    historyBusyRef.current = true;
    setHistoryMutation({ id, kind: "update" });
    try {
      await updateHistoryAssets(id, patch);
      const merge = (item: HistoryItem) => item.session_id === id ? { ...item, ...patch } : item;
      setHistory((items) => items.map(merge));
      setHistorySearchResults((items) => items?.map(merge) ?? null);
      if (patch.title !== undefined) {
        setTurns((items) => items.map((turn) => ((turn.sessionId ?? turn.id) === id ? { ...turn, query: patch.title! } : turn)));
      }
      notify(patch.archived === true ? "Research archived" : patch.archived === false ? "Research restored" : "Research details saved", "success");
      void refreshHistory();
    } catch (error) {
      notify(`Couldn’t update this research: ${error instanceof Error ? error.message : String(error)}. No changes were saved.`);
    } finally {
      historyBusyRef.current = false;
      setHistoryMutation(null);
    }
  }, [notify, refreshHistory]);

  const handleDelete = useCallback(async (id: string) => {
    if (historyBusyRef.current) return;
    historyBusyRef.current = true;
    setHistoryMutation({ id, kind: "delete" });
    try {
      await deleteHistory(id);
      setHistory((prev) => prev.filter((h) => h.session_id !== id));
      setHistorySearchResults((prev) => prev?.filter((h) => h.session_id !== id) ?? null);
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
    const source = historySearchResults ?? history;
    const items = source.map((h) => ({
      id: h.session_id,
      title: h.title,
      status: restoredRunState(h.status).status,
      coverageScore: h.coverage_score,
      updatedAt: h.updated_at,
      project: h.project,
      tags: h.tags,
      favorite: h.favorite,
      archived: h.archived,
    }));
    if (openTurn && openTurn.status === "running") {
      const sid = openTurn.sessionId ?? openTurn.id;
      if (!items.some((i) => i.id === sid)) items.unshift({
        id: sid, title: openTurn.query, status: "running", coverageScore: null,
        updatedAt: Date.now() / 1000, project: "", tags: [], favorite: false, archived: false,
      });
    }
    return items;
  }, [history, historySearchResults, openTurn]);
  const projects = useMemo(() => Array.from(new Set(history.map((item) => item.project).filter(Boolean))).sort(), [history]);
  const projectFacets = useMemo(() => projects.map((name) => ({
    name,
    count: history.filter((item) => !item.archived && item.project === name).length,
  })), [history, projects]);
  const tagFacets = useMemo(() => {
    const counts = new Map<string, number>();
    history.filter((item) => !item.archived).forEach((item) => item.tags.forEach((tag) => {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }));
    return Array.from(counts, ([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [history]);
  const assetCounts = useMemo(() => ({
    all: history.filter((item) => !item.archived).length,
    favorites: history.filter((item) => item.favorite && !item.archived).length,
    archived: history.filter((item) => item.archived).length,
    attention: history.filter((item) => !item.archived && (
      item.status !== "completed" || (item.coverage_score != null && item.coverage_score < 0.999)
    )).length,
    unassigned: history.filter((item) => !item.archived && !item.project).length,
  }), [history]);

  const drawerOpen = !!drawerTurn;
  const latestEditableTurn = [...turns].reverse().find((turn) => (
    turn.status === "completed" && !!turn.sessionId && !!turn.searchState
  ));
  const drawerEditable = !sessionActive && latestEditableTurn?.id === drawerTurn?.id;

  const executionPanel = drawerTurn && (
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
            onOpenLocalSource={setLocalSourceRef}
            onSelectTurn={handleOpenDrawer}
            onBranchTurn={sessionActive ? undefined : handleBranchTurn}
            branchingTurnId={branchingTurnId}
            subagentsCollapsed={mobile ? mobileAgentsCollapsed : activityPreferences.subagentsCollapsed}
            onSubagentsCollapsedChange={(subagentsCollapsed) => mobile ? setMobileAgentsCollapsed(subagentsCollapsed) : updateActivityPreferences({ subagentsCollapsed })}
          />
        );

  if (mobile) return <MobileAssistant
    turns={turns} history={history} historyStatus={historyStatus} loadingId={historyLoadingId}
    running={sessionActive} reconnecting={session.status === "reconnecting"} stopping={stopPending}
    error={session.error} localLibrary={localLibrary} onSubmit={handleSubmit} onSteer={handleSteer}
    onRerun={(query, opts) => handleSubmit(query, opts, true)}
    onStop={handleStop} onNew={handleNew} onOpen={handleSelect} onRefresh={handleRetryHistory}
    onDetails={handleOpenDrawer} onOpenSource={setLocalSourceRef}
  >
    {drawerTurn && <div className="research-workspace fixed inset-0 z-50" data-mobile-workspace="forced"><div className="workspace-activity h-full">{executionPanel}</div></div>}
    {localSourceRef && <SourcePanel key={localSourceRef} refId={localSourceRef} onClose={() => setLocalSourceRef(null)} />}
  </MobileAssistant>;

  return (
    <div
      data-mobile-workspace={mobile ? "forced" : "responsive"}
      className={`research-workspace grid h-[100dvh] grid-rows-[minmax(0,1fr)] overflow-hidden grid-cols-[minmax(0,1fr)] ${mobile ? "" : "min-[1180px]:grid-cols-[var(--rail-width)_minmax(0,1fr)_var(--drawer-width)]"} ${drawerResizing ? "" : "transition-[grid-template-columns] duration-300 ease-out"}`}
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
          onClick={closeMobileRail}
          className={`fade-in fixed inset-0 z-40 bg-ink/20 ${mobile ? "" : "min-[1180px]:hidden"} dark:bg-black/50`}
        />
      )}

      <aside
        ref={mobileRailRef}
        role={mobileRailOpen ? "dialog" : undefined}
        aria-modal={mobileRailOpen || undefined}
        aria-label={zh ? "历史与导航" : "History and navigation"}
        tabIndex={-1}
        className={`workspace-history min-h-0 overflow-hidden ${
          mobileRailOpen
            ? "fixed inset-y-0 left-0 z-50 block w-[min(320px,88vw)] bg-paper shadow-2xl"
            : "hidden"
        } ${mobile ? "" : "min-[1180px]:static min-[1180px]:z-auto min-[1180px]:block min-[1180px]:w-auto min-[1180px]:shadow-none"}`}
      >
        {mobileRailOpen && <div className="workspace-history-heading">
          <span>{zh ? "历史与导航" : "History & navigation"}</span>
          <button ref={mobileRailCloseRef} type="button" onClick={closeMobileRail} aria-label={zh ? "关闭历史与导航" : "Close history and navigation"}><X size={20} /></button>
        </div>}
        <div className="workspace-history-content">
        <HistoryRail
          items={railItems}
          activeId={openId}
          collapsed={mobileRailOpen ? false : railCollapsed}
          onToggle={() => mobileRailOpen ? setMobileRailOpen(false) : setRailCollapsed((v) => !v)}
          onNew={() => { setMobileRailOpen(false); handleNew(); }}
          onSelect={(id) => { setMobileRailOpen(false); void handleSelect(id); }}
          onUpdateAssets={(id, patch) => { void handleUpdateHistoryAssets(id, patch); }}
          onDelete={(id) => { void handleDelete(id); }}
          onOpenKnowledgeBase={() => { setMobileRailOpen(false); setKnowledgeBaseOpen(true); }}
          projects={projectFacets}
          tags={tagFacets}
          assetCounts={assetCounts}
          searchQuery={historyQuery}
          searching={historySearching}
          onSearch={setHistoryQuery}
          onOpenSettings={() => { setMobileRailOpen(false); setSettingsOpen(true); }}
          loadingId={historyLoadingId}
          mutation={historyMutation}
          historyStatus={historyStatus}
          onRetryHistory={handleRetryHistory}
        />
        </div>
      </aside>

      <main className="workspace-main relative min-h-0 min-w-0 overflow-hidden">
        <header className={`workspace-mobile-header ${mobile ? "" : "min-[1180px]:hidden"}`}>
          <button ref={mobileRailTriggerRef} type="button" aria-label={zh ? "打开历史与导航" : "Open history and navigation"} onClick={() => setMobileRailOpen(true)}><Menu size={20} /></button>
          <div className="workspace-mobile-brand"><span className="wordmark">SearchOS</span><span className="workspace-connection" data-status={backendStatus}>{backendStatus === "ready" ? (zh ? "已连接" : "Connected") : backendStatus === "offline" ? (zh ? "后端未连接" : "Backend offline") : (zh ? "连接中" : "Connecting")}</span></div>
          <button type="button" onClick={handleNew} aria-label={zh ? "新建研究" : "New research"}><Plus size={21} /></button>
        </header>
        {turns.length === 0 ? (
          <Landing onSubmit={handleSubmit} error={session.error} localLibrary={localLibrary} />
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
            localLibrary={localLibrary}
            onOpenLocalSource={setLocalSourceRef}
          />
        )}
      </main>

      <div className={`workspace-activity ${drawerTurn ? "fixed inset-0 z-40" : "hidden"} min-h-0 min-w-0 overflow-hidden ${mobile ? "" : "min-[1180px]:static min-[1180px]:z-auto min-[1180px]:block"}`}>
        {executionPanel}
      </div>

      <nav className={`workspace-mobile-nav ${mobile ? "" : "min-[1180px]:hidden"}`} aria-label={zh ? "工作区导航" : "Workspace navigation"}>
        <button type="button" aria-current={!mobileRailOpen && !drawerTurn && !knowledgeBaseOpen && !settingsOpen ? "page" : undefined} onClick={() => { setMobileRailOpen(false); setDrawerTurnId(null); setKnowledgeBaseOpen(false); setSettingsOpen(false); }}><MessageSquare size={20} /><span>{zh ? "研究" : "Research"}</span></button>
        <button type="button" aria-expanded={mobileRailOpen} onClick={() => setMobileRailOpen(true)}><History size={20} /><span>{zh ? "历史" : "History"}</span></button>
        <button type="button" aria-expanded={knowledgeBaseOpen} onClick={() => setKnowledgeBaseOpen(true)}><Database size={20} /><span>{zh ? "知识库" : "Library"}</span></button>
        <button type="button" disabled={!turns.length} aria-expanded={!!drawerTurn} title={!turns.length ? (zh ? "开始研究或打开历史后查看" : "Start research or open history first") : undefined} onClick={() => { const target = turns.find(t => t.id === activeTurnId) ?? turns[turns.length - 1]; if (target) handleOpenDrawer(target.id); }}><Activity size={20} /><span>{zh ? "详情" : "Activity"}</span></button>
        <button type="button" aria-expanded={settingsOpen} onClick={() => setSettingsOpen(true)}><Settings2 size={20} /><span>{zh ? "设置" : "Settings"}</span></button>
      </nav>
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      {knowledgeBaseOpen && <KnowledgeBasePanel controller={localLibrary} onClose={() => setKnowledgeBaseOpen(false)} />}
      {localSourceRef && <SourcePanel key={localSourceRef} refId={localSourceRef} onClose={() => setLocalSourceRef(null)} />}
    </div>
  );
}
