"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import type { RepairRequest, SearchRequest, SearchResult, SearchState, WorkerInfo, WSEvent } from "@/lib/types";
import { applyStateChanges, advanceAnswer, olderRevision, type StateChange } from "@/lib/liveUpdates";
import { finalizeWorkers, foldWorkers, updateWorkersBatch } from "@/lib/derive";
import { startSearch, startRepair, getSearchResult, getSearchState, connectWebSocket, type RepairStartResponse } from "@/lib/api";
export interface SearchSession {
  sessionId: string | null;
  status: "idle" | "running" | "reconnecting" | "completed" | "error";
  result: SearchResult | null;
  liveState: SearchState | null;
  events: WSEvent[];
  workers: WorkerInfo[];
  error: string | null;
  elapsed: number;
  liveAnswer: string | null;
  startedAt?: number;
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000, 15000];

function eventSignature(event: WSEvent): string {
  return typeof event.event_id === "string" ? event.event_id : JSON.stringify(event);
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
    liveAnswer: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const eventQueueRef = useRef<WSEvent[]>([]);
  const flushEventsRef = useRef<() => void>(() => {});
  const answerRef = useRef({ streamId: "", answer: "" });
  const revisionRef = useRef("");
  const socketStateRef = useRef<{ revision: string; state: SearchState } | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startTimeRef = useRef<number>(0);
  const generationRef = useRef(0);
  const terminalRef = useRef(false);
  const snapshotRequestRef = useRef(0);
  const appliedSnapshotRef = useRef(0);
  const reconnectAttemptRef = useRef(0);
  const statusCheckRef = useRef<Promise<"running" | "terminal" | "unavailable" | "stale"> | null>(null);
  // 重连会重放历史；用完整事件去重。
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
    if (batchTimerRef.current) clearTimeout(batchTimerRef.current);
    eventQueueRef.current = [];
    batchTimerRef.current = null;
    revisionRef.current = "";
    socketStateRef.current = null;
    answerRef.current = { streamId: "", answer: "" };
    if (pollRef.current) clearInterval(pollRef.current);
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);

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

  const applyLiveState = useCallback((sessionId: string, generation: number, request: number, state: SearchState | null | undefined, revision?: string) => {
    if (state === undefined || generation !== generationRef.current || terminalRef.current || request < appliedSnapshotRef.current) return;
    if (revision && olderRevision(revision, revisionRef.current)) return;
    if (revision) revisionRef.current = revision;
    appliedSnapshotRef.current = request;
    setSession((current) => {
      if (generation !== generationRef.current || terminalRef.current || current.sessionId !== sessionId || request !== appliedSnapshotRef.current) return current;
      // 后端快照允许清空单元格和撤销证据；顺序由请求编号控制。
      return { ...current, liveState: state };
    });
  }, []);

  const reconcileStatus = useCallback((sessionId: string, generation: number) => {
    if (generation !== generationRef.current || terminalRef.current) {
      return Promise.resolve("stale" as const);
    }
    if (statusCheckRef.current) return statusCheckRef.current;

    const check = (async (): Promise<"running" | "terminal" | "unavailable" | "stale"> => {
      try {
        const request = ++snapshotRequestRef.current;
        const result = await getSearchResult(sessionId);
        if (generation !== generationRef.current || terminalRef.current) return "stale";

        if (result.status === "running") {
          applyLiveState(sessionId, generation, request, result.search_state, result.revision);
          return "running";
        }

        flushEventsRef.current();
        terminalRef.current = true;
        clearRuntime();
        setSession((current) => {
          if (generation !== generationRef.current || current.sessionId !== sessionId) return current;
          return {
            ...current,
            status: result.status === "error" ? "error" : "completed",
            result,
            workers: finalizeWorkers(current.workers, result.status === "error" ? "error" : "completed"),
            liveState: result.search_state ?? null,
            elapsed: result.elapsed_s ?? (Date.now() - startTimeRef.current) / 1000,
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
  }, [applyLiveState, clearRuntime]);

  const openSocketRef = useRef<(sessionId: string, generation: number, tail: boolean) => void>(() => {});

  const scheduleReconnect = useCallback((sessionId: string, generation: number) => {
    if (generation !== generationRef.current || terminalRef.current || reconnectTimerRef.current) return;

    setSession((current) => {
      if (current.sessionId !== sessionId || current.status === "completed" || current.status === "error") return current;
      return { ...current, status: "reconnecting" };
    });

    // 状态查询与重连并行，终态会取消重试。
    void reconcileStatus(sessionId, generation);

    const attempt = reconnectAttemptRef.current;
    const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
    reconnectAttemptRef.current = attempt + 1;
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      if (generation === generationRef.current && !terminalRef.current) {
        // 重放并去重，补回断线期间的事件。
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
          if (event.type === "state_snapshot") {
            socketStateRef.current = { revision: String(event.revision), state: event.state as SearchState };
            applyLiveState(sessionId, generation, ++snapshotRequestRef.current, event.state as SearchState, String(event.revision));
            return;
          }
          if (event.type === "state_delta") {
            const baseline = socketStateRef.current;
            if (!baseline || baseline.revision !== event.base_revision) {
              // Reconnect obtains a fresh baseline and replays durable events.
              ws.close();
              return;
            }
            try {
              const state = applyStateChanges(baseline.state, event.changes as StateChange[]);
              socketStateRef.current = { revision: String(event.revision), state };
              applyLiveState(sessionId, generation, ++snapshotRequestRef.current, state, String(event.revision));
            } catch { ws.close(); }
            return;
          }
          const signature = eventSignature(nextEvent);
          if (seenRef.current.has(signature)) return;
          seenRef.current.add(signature);

          eventQueueRef.current.push(nextEvent);
          const flush = () => {
            batchTimerRef.current = null;
            if (generation !== generationRef.current || terminalRef.current) return;
            const batch = eventQueueRef.current.splice(0);
            if (!batch.length) return;
            answerRef.current = advanceAnswer(answerRef.current, batch);
            const liveAnswer = answerRef.current.streamId ? answerRef.current.answer : null;
            setSession((current) => {
              if (current.sessionId !== sessionId) return current;
              return { ...current, events: [...current.events, ...batch],
                workers: updateWorkersBatch(current.workers, batch), liveAnswer,
                elapsed: (Date.now() - startTimeRef.current) / 1000 };
            });
          };
          flushEventsRef.current = flush;
          if (nextEvent.type === "search_complete" || nextEvent.type === "search_error") {
            if (batchTimerRef.current) clearTimeout(batchTimerRef.current);
            flush();
            void reconcileStatus(sessionId, generation);
          } else if (batchTimerRef.current === null) batchTimerRef.current = setTimeout(flush, 32);

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
  }, [applyLiveState, reconcileStatus, scheduleReconnect]);
  openSocketRef.current = openSocket;

  /** 新任务和重新连接共用计时、轮询与订阅。 */
  const startStreams = useCallback((sessionId: string, tail: boolean, generation: number) => {
    startTimeRef.current = Date.now();
    setSession((current) => ({ ...current, startedAt: startTimeRef.current }));
    let pollInFlight = false;

    const poll = async () => {
      if (pollInFlight || generation !== generationRef.current || terminalRef.current) return;
      pollInFlight = true;
      try {
        const request = ++snapshotRequestRef.current;
        const result = await getSearchState(sessionId, revisionRef.current);
        if (generation !== generationRef.current || terminalRef.current) return;
        applyLiveState(sessionId, generation, request, result.search_state, result.revision);
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
  }, [applyLiveState, openSocket, reconcileStatus]);

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
      liveAnswer: null,
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

  /** 恢复运行中的会话；若 events 只含当前轮次，seen 应传完整日志以避免重放重复。 */
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
      answerRef.current = advanceAnswer({ streamId: "", answer: "" }, events);
      seenRef.current = new Set((seed?.seen ?? events).map(eventSignature));
      setSession({
        sessionId: session_id,
        status: "running",
        result: null,
        liveState: seed?.searchState ?? null,
        events,
        workers: foldWorkers(events),
        error: null,
        elapsed: 0,
        liveAnswer: answerRef.current.streamId ? answerRef.current.answer : null,
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
      liveAnswer: null,
    });
  }, [clearRuntime]);

  return { session, run, repair, attach, reset };
}
