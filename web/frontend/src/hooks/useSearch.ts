"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import type { RepairRequest, SearchRequest, SearchResult, SearchState, WSEvent } from "@/lib/types";
import { startSearch, startRepair, getSearchResult, getSearchState, connectWebSocket, type RepairStartResponse } from "@/lib/api";


/**
 * Optimistic merge: keep the "best" version of each cell.
 * A filled cell never reverts to missing, even if the backend sends an
 * intermediate state snapshot where a parallel agent hasn't written yet.
 */
function mergeSearchState(
  prev: SearchState | null | undefined,
  incoming: SearchState | null | undefined,
): SearchState | null {
  if (!incoming) return prev ?? null;
  if (!prev) return incoming;

  // Merge coverage_map cells: keep filled cells from prev if incoming has them as missing
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const prevCells = (prev.coverage_map?.cells ?? {}) as Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const incomingCells = (incoming.coverage_map?.cells ?? {}) as Record<string, any>;
  const mergedCells = { ...incomingCells };

  for (const [key, pc] of Object.entries(prevCells)) {
    const ic = mergedCells[key];
    if (pc?.status === "filled" && (!ic || ic?.status === "missing")) {
      mergedCells[key] = pc;
    }
  }

  const prevEv = prev.evidence_graph?.nodes ?? [];
  const incEv = incoming.evidence_graph?.nodes ?? [];

  return {
    ...incoming,
    coverage_map: {
      ...incoming.coverage_map,
      cells: mergedCells,
    } as SearchState["coverage_map"],
    evidence_graph: incEv.length >= prevEv.length
      ? incoming.evidence_graph
      : prev.evidence_graph,
  };
}

export interface WorkerInfo {
  name: string;
  intent: string;
  scope: string;
  status: "pending" | "running" | "completed" | "error";
  events: WSEvent[];
}

export interface SearchSession {
  sessionId: string | null;
  status: "idle" | "running" | "reconnecting" | "completed" | "error";
  result: SearchResult | null;
  liveState: SearchState | null;
  events: WSEvent[];
  workers: WorkerInfo[];
  error: string | null;
  elapsed: number;
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000, 15000];

function eventSignature(event: WSEvent): string {
  return JSON.stringify(event);
}

/** When a search ends, no sub-agent is still in flight: coerce any straggler
 *  left "running"/"pending" (missing a terminal event) to completed. */
function finalizeWorkers(workers: WorkerInfo[]): WorkerInfo[] {
  return workers.map((w) =>
    w.status === "running" || w.status === "pending" ? { ...w, status: "completed" } : w,
  );
}

export function useSearch() {
  const [session, setSession] = useState<SearchSession>({
    sessionId: null,
    status: "idle",
    result: null,
    liveState: null,
    events: [],
    workers: [],
    error: null,
    elapsed: 0,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startTimeRef = useRef<number>(0);
  const generationRef = useRef(0);
  const terminalRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const statusCheckRef = useRef<Promise<"running" | "terminal" | "unavailable" | "stale"> | null>(null);
  // Dedupe re-streamed events: a WS reconnect re-reads trajectory.jsonl from
  // the top, so every prior event arrives again. Each event's full payload
  // (incl. timestamp/step_index) is a stable signature.
  const seenRef = useRef<Set<string>>(new Set());

  const disposeSocket = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (!ws) return;
    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    if (ws.readyState < WebSocket.CLOSING) ws.close();
  }, []);

  const clearRuntime = useCallback(() => {
    disposeSocket();
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    timerRef.current = null;
    pollRef.current = null;
    reconnectTimerRef.current = null;
  }, [disposeSocket]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      generationRef.current += 1;
      clearRuntime();
    };
  }, [clearRuntime]);

  const reconcileStatus = useCallback((sessionId: string, generation: number) => {
    if (generation !== generationRef.current || terminalRef.current) {
      return Promise.resolve("stale" as const);
    }
    if (statusCheckRef.current) return statusCheckRef.current;

    const check = (async (): Promise<"running" | "terminal" | "unavailable" | "stale"> => {
      try {
        const result = await getSearchResult(sessionId);
        if (generation !== generationRef.current || terminalRef.current) return "stale";

        if (result.status === "running") {
          if (result.search_state) {
            setSession((current) => current.sessionId === sessionId
              ? { ...current, liveState: mergeSearchState(current.liveState, result.search_state) }
              : current);
          }
          return "running";
        }

        terminalRef.current = true;
        clearRuntime();
        setSession((current) => {
          if (current.sessionId !== sessionId) return current;
          return {
            ...current,
            status: result.status === "error" ? "error" : "completed",
            result,
            workers: finalizeWorkers(current.workers),
            liveState: mergeSearchState(current.liveState, result.search_state),
            error: result.error || null,
          };
        });
        return "terminal";
      } catch {
        return "unavailable";
      }
    })();

    statusCheckRef.current = check;
    void check.finally(() => {
      if (statusCheckRef.current === check) statusCheckRef.current = null;
    });
    return check;
  }, [clearRuntime]);

  const openSocketRef = useRef<(sessionId: string, generation: number, tail: boolean) => void>(() => {});

  const scheduleReconnect = useCallback((sessionId: string, generation: number) => {
    if (generation !== generationRef.current || terminalRef.current || reconnectTimerRef.current) return;

    setSession((current) => {
      if (current.sessionId !== sessionId || current.status === "completed" || current.status === "error") return current;
      return { ...current, status: "reconnecting" };
    });

    // Reconnect and terminal reconciliation run in parallel: a slow/unreachable
    // REST endpoint must not hold the socket retry loop hostage. A confirmed
    // terminal result calls clearRuntime(), cancelling the pending retry.
    void reconcileStatus(sessionId, generation);

    const attempt = reconnectAttemptRef.current;
    const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
    reconnectAttemptRef.current = attempt + 1;
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      if (generation === generationRef.current && !terminalRef.current) {
        // Replay from the start and dedupe locally so events produced during
        // the outage are recovered rather than skipped.
        openSocketRef.current(sessionId, generation, false);
      }
    }, delay);
  }, [reconcileStatus]);

  const openSocket = useCallback((sessionId: string, generation: number, tail: boolean) => {
    if (generation !== generationRef.current || terminalRef.current) return;
    let closeHandled = false;

    try {
      const ws = connectWebSocket(
        sessionId,
        (event) => {
          if (generation !== generationRef.current || wsRef.current !== ws || terminalRef.current) return;
          const nextEvent = event as WSEvent;
          const signature = eventSignature(nextEvent);
          if (seenRef.current.has(signature)) return;
          seenRef.current.add(signature);

          setSession((current) => {
            if (current.sessionId !== sessionId) return current;
            return {
              ...current,
              events: [...current.events, nextEvent],
              workers: updateWorkers(current.workers, nextEvent),
            };
          });

          if (nextEvent.type === "search_complete" || nextEvent.type === "search_error") {
            void reconcileStatus(sessionId, generation);
          }
        },
        () => {
          if (closeHandled || generation !== generationRef.current || wsRef.current !== ws) return;
          closeHandled = true;
          wsRef.current = null;
          scheduleReconnect(sessionId, generation);
        },
        {
          tail,
          onOpen: () => {
            if (generation !== generationRef.current || wsRef.current !== ws || terminalRef.current) return;
            reconnectAttemptRef.current = 0;
            setSession((current) => current.sessionId === sessionId && current.status === "reconnecting"
              ? { ...current, status: "running" }
              : current);
          },
        },
      );
      wsRef.current = ws;
    } catch {
      scheduleReconnect(sessionId, generation);
    }
  }, [reconcileStatus, scheduleReconnect]);
  openSocketRef.current = openSocket;

  /** Timer + state poll + WS subscription for a session the backend is
   *  already running. Shared by run() (fresh POST) and attach() (reopen). */
  const startStreams = useCallback((sessionId: string, tail: boolean, generation: number) => {
    startTimeRef.current = Date.now();
    let pollInFlight = false;

    timerRef.current = setInterval(() => {
      setSession((current) => {
        if (current.sessionId !== sessionId || (current.status !== "running" && current.status !== "reconnecting")) return current;
        return { ...current, elapsed: (Date.now() - startTimeRef.current) / 1000 };
      });
    }, 500);

    const poll = async () => {
      if (pollInFlight || generation !== generationRef.current || terminalRef.current) return;
      pollInFlight = true;
      try {
        const result = await getSearchState(sessionId);
        if (generation !== generationRef.current || terminalRef.current) return;
        if (result.search_state) {
          setSession((current) => current.sessionId === sessionId
            ? { ...current, liveState: mergeSearchState(current.liveState, result.search_state) }
            : current);
        }
        if (result.status === "completed" || result.status === "error") {
          void reconcileStatus(sessionId, generation);
        }
      } catch {
        // A transient REST failure should not terminate an otherwise live run.
      } finally {
        pollInFlight = false;
      }
    };

    void poll();
    pollRef.current = setInterval(poll, 2000);
    openSocket(sessionId, generation, tail);
  }, [openSocket, reconcileStatus]);

  const beginRun = useCallback(async ({
    start,
    seen = [],
    initialState = null,
    knownSessionId = null,
    tail = false,
    failureStatus = "error",
    onStarted,
  }: {
    start: () => Promise<{ session_id: string }>;
    seen?: WSEvent[];
    initialState?: SearchState | null;
    knownSessionId?: string | null;
    tail?: boolean;
    failureStatus?: "idle" | "error";
    onStarted?: (response: { session_id: string; [key: string]: unknown }) => void;
  }) => {
    const generation = ++generationRef.current;
    clearRuntime();
    terminalRef.current = false;
    reconnectAttemptRef.current = 0;
    statusCheckRef.current = null;
    seenRef.current = new Set(seen.map(eventSignature));

    setSession({
      sessionId: knownSessionId,
      status: "running",
      result: null,
      liveState: initialState,
      events: [],
      workers: [],
      error: null,
      elapsed: 0,
    });

    try {
      const response = await start();
      const { session_id } = response;
      if (generation !== generationRef.current) return null;
      onStarted?.(response);
      setSession((s) => ({ ...s, sessionId: session_id }));
      startStreams(session_id, tail, generation);
      return null;
    } catch (e) {
      if (generation !== generationRef.current) return null;
      clearRuntime();
      const msg = e instanceof TypeError
        ? "Backend unreachable — run ./start.sh api"
        : e instanceof Error ? e.message : String(e);
      setSession((s) => ({
        ...s,
        status: failureStatus,
        error: msg,
      }));
      return msg;
    }
  }, [clearRuntime, startStreams]);

  const run = useCallback((req: SearchRequest, opts?: { seen?: WSEvent[] }) => beginRun({
    start: () => startSearch(req),
    seen: opts?.seen,
    tail: !!req.follow_up_to,
    failureStatus: "idle",
  }), [beginRun]);

  const repair = useCallback((
    sessionId: string,
    req: RepairRequest,
    opts?: {
      seen?: WSEvent[];
      initialState?: SearchState | null;
      onStarted?: (response: RepairStartResponse) => void;
    },
  ) => beginRun({
    start: () => startRepair(sessionId, req),
    seen: opts?.seen,
    initialState: opts?.initialState,
    knownSessionId: sessionId,
    tail: false,
    failureStatus: "error",
    onStarted: (response) => opts?.onStarted?.(response as unknown as RepairStartResponse),
  }), [beginRun]);

  /** Re-attach to a session the backend is still running — history reopen,
   *  or switching back to a live run after navigating away. Seeds the
   *  already-recorded events, then streams live; the WS replay is deduped
   *  against `seen` (defaults to the seed) so nothing doubles and the
   *  snapshot gap is closed. Pass the full log as `seen` when seeding only
   *  the current turn's segment. */
  const attach = useCallback(
    (
      session_id: string,
      seed?: { events?: WSEvent[]; searchState?: SearchState | null; seen?: WSEvent[] },
    ) => {
      const generation = ++generationRef.current;
      clearRuntime();
      terminalRef.current = false;
      reconnectAttemptRef.current = 0;
      statusCheckRef.current = null;

      const events = seed?.events ?? [];
      seenRef.current = new Set((seed?.seen ?? events).map(eventSignature));
      setSession({
        sessionId: session_id,
        status: "running",
        result: null,
        liveState: seed?.searchState ?? null,
        events,
        workers: events.reduce((w, e) => updateWorkers(w, e), [] as WorkerInfo[]),
        error: null,
        elapsed: 0,
      });
      startStreams(session_id, false, generation);
    },
    [clearRuntime, startStreams],
  );

  const reset = useCallback(() => {
    generationRef.current += 1;
    clearRuntime();
    terminalRef.current = false;
    reconnectAttemptRef.current = 0;
    statusCheckRef.current = null;
    seenRef.current = new Set();
    setSession({
      sessionId: null,
      status: "idle",
      result: null,
      liveState: null,
      events: [],
      workers: [],
      error: null,
      elapsed: 0,
    });
  }, [clearRuntime]);

  return { session, run, repair, attach, reset };
}

/**
 * Aggregate per-sub-agent activity from the event stream.
 *
 * Sub-agents are identified by the `agent` field on trajectory events
 * (`warmup_agent`, `search_agent_2`, `writer_agent`, …). The orchestrator's
 * own steps (`agent === "orchestrator"`) drive the timeline, not a card,
 * so they are excluded here. Blackboard streams (when present) carry the
 * same `agent` field and are folded in too.
 */
function updateWorkers(current: WorkerInfo[], event: WSEvent): WorkerInfo[] {
  const etype = String(event.type || "");
  const isTraj = etype === "trajectory";
  const isBlackboard = etype.startsWith("blackboard.");
  if (!isTraj && !isBlackboard) return current;

  const data = (event.data ?? {}) as Record<string, unknown>;
  const agent = String(data.agent || data.worker || data.agent_name || "");
  if (!agent || agent === "orchestrator") return current;

  // Pure update — never mutate the existing worker objects. React (esp. Strict
  // Mode) may invoke this updater twice with the same prior state; mutating in
  // place would append the event twice → duplicated trace/card lines.
  const idx = current.findIndex((w) => w.name === agent);
  const prev = idx >= 0 ? current[idx] : null;

  const dtype = String(data.type || "");
  const status = String(data.status || "");
  let nextStatus = prev?.status ?? "running";
  if (dtype === "agent_complete" || dtype === "agent_final" || status === "completed" || status === "partial") {
    nextStatus = "completed";
  }
  if (dtype === "agent_error" || dtype === "error" || status === "error") {
    nextStatus = "error";
  }

  const updated: WorkerInfo = {
    name: agent,
    intent:
      prev?.intent ??
      (agent.startsWith("warmup") ? "explore" : agent.startsWith("writer") ? "write" : "search"),
    scope: prev?.scope ?? agent,
    status: nextStatus,
    events: prev ? [...prev.events, event] : [event],
  };

  if (idx >= 0) {
    const copy = [...current];
    copy[idx] = updated;
    return copy;
  }
  return [...current, updated];
}
