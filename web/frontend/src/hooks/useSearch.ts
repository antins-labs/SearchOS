"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import type { SearchRequest, SearchResult, SearchState, WSEvent } from "@/lib/types";
import { startSearch, getSearchResult, getSearchState, connectWebSocket } from "@/lib/api";


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
  status: "idle" | "running" | "completed" | "error";
  result: SearchResult | null;
  liveState: SearchState | null;
  events: WSEvent[];
  workers: WorkerInfo[];
  error: string | null;
  elapsed: number;
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
  const startTimeRef = useRef<number>(0);
  // Dedupe re-streamed events: a WS reconnect re-reads trajectory.jsonl from
  // the top, so every prior event arrives again. Each event's full payload
  // (incl. timestamp/step_index) is a stable signature.
  const seenRef = useRef<Set<string>>(new Set());

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      if (timerRef.current) clearInterval(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const run = useCallback(async (req: SearchRequest) => {
    // Cleanup previous
    wsRef.current?.close();
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);
    seenRef.current = new Set();

    setSession({
      sessionId: null,
      status: "running",
      result: null,
      liveState: null,
      events: [],
      workers: [],
      error: null,
      elapsed: 0,
    });

    try {
      const { session_id } = await startSearch(req);
      startTimeRef.current = Date.now();

      setSession((s) => ({ ...s, sessionId: session_id }));

      // Timer: update elapsed every 500ms
      timerRef.current = setInterval(() => {
        setSession((s) => ({
          ...s,
          elapsed: (Date.now() - startTimeRef.current) / 1000,
        }));
      }, 500);

      // Poll state every 2s for real-time Coverage/Evidence updates.
      // Use optimistic merge: only "upgrade" cell states (missing→filled),
      // never "downgrade" (filled→missing). This prevents visual flickering
      // when multiple parallel sub_agents write to state concurrently.
      pollRef.current = setInterval(() => {
        getSearchState(session_id)
          .then((res) => {
            if (res.search_state) {
              setSession((s) => {
                if (s.sessionId !== session_id || s.status !== "running") return s;
                const incoming = res.search_state as SearchState;
                const merged = mergeSearchState(s.liveState, incoming);
                return { ...s, liveState: merged };
              });
            }
          })
          .catch(() => {});
      }, 2000);

      // WebSocket for event stream
      const ws = connectWebSocket(
        session_id,
        (event) => {
          const e = event as WSEvent;
          // Drop duplicates from WS reconnects (terminal events always pass).
          if (e.type !== "search_complete" && e.type !== "search_error") {
            const sig = `${e.type}|${JSON.stringify(
              (e as Record<string, unknown>).data ?? (e as Record<string, unknown>).node ?? "",
            )}`;
            if (seenRef.current.has(sig)) return;
            seenRef.current.add(sig);
          }
          setSession((s) => {
            const newEvents = [...s.events, e];
            const newWorkers = updateWorkers(s.workers, e);

            // Search finished
            if (e.type === "search_complete" || e.type === "search_error") {
              if (timerRef.current) clearInterval(timerRef.current);
              if (pollRef.current) clearInterval(pollRef.current);
              getSearchResult(session_id).then((result) => {
                setSession((s2) => {
                  if (s2.sessionId !== session_id) return s2;
                  return {
                    ...s2,
                    status: result.status === "error" ? "error" : "completed",
                    result,
                    workers: finalizeWorkers(s2.workers),
                    liveState: mergeSearchState(s2.liveState, result.search_state as SearchState) || s2.liveState,
                    error: result.error || null,
                  };
                });
              }).catch(() => {
                setSession((s2) => {
                  if (s2.sessionId !== session_id) return s2;
                  return { ...s2, status: "error", error: "Failed to fetch final result" };
                });
              });
            }

            return { ...s, events: newEvents, workers: newWorkers };
          });
        },
        () => {
          if (timerRef.current) clearInterval(timerRef.current);
          if (pollRef.current) clearInterval(pollRef.current);
          getSearchResult(session_id).then((result) => {
            setSession((s) => {
              if (s.sessionId !== session_id) return s;
              return {
                ...s,
                status: result.status === "error" ? "error" : "completed",
                result,
                workers: finalizeWorkers(s.workers),
                liveState: result.search_state as SearchState || s.liveState,
              };
            });
          }).catch(() => {});
        },
      );
      wsRef.current = ws;
    } catch (e) {
      if (timerRef.current) clearInterval(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
      const msg = e instanceof TypeError
        ? "Backend unreachable — run ./start.sh api"
        : e instanceof Error ? e.message : String(e);
      // POST never succeeded: drop back to the entry screen instead of an empty workbench
      setSession((s) => ({
        ...s,
        status: s.sessionId ? "error" : "idle",
        error: msg,
      }));
    }
  }, []);

  const reset = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);
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
  }, []);

  return { session, run, reset };
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
