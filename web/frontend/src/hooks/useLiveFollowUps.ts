"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getSteeringQueue, isSteeringSnapshot, promoteSteeringMessage, removeSteeringMessage, steerSearch } from "@/lib/api";
import type { SteeringMode, SteeringSnapshot } from "@/lib/types";

export function useLiveFollowUps(
  sessionId: string | null,
  turnId: string | null,
  running: boolean,
  notify: (message: string) => void,
) {
  const scope = `${sessionId ?? ""}:${turnId ?? ""}`;
  const scopeRef = useRef(scope);
  const [snapshot, setSnapshot] = useState<{ scope: string; value: SteeringSnapshot } | null>(null);
  const inFlight = useRef(new Set<string>());
  const [operations, setOperations] = useState<Set<string>>(new Set());

  const accept = useCallback((value: unknown) => {
    if (scopeRef.current !== scope || !isSteeringSnapshot(value)) return;
    setSnapshot((previous) => (
      previous?.scope === scope && isSteeringSnapshot(previous.value)
        && previous.value.revision >= value.revision
        ? previous : { scope, value }
    ));
  }, [scope]);

  useEffect(() => {
    scopeRef.current = scope;
    if (!sessionId || !turnId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const value = await getSteeringQueue(sessionId);
        if (!disposed) accept(value);
      } catch {
        // Keep pending rows through transient reconnects and old backend sessions.
      } finally {
        if (!disposed && running) timer = setTimeout(refresh, 1000);
      }
    };
    void refresh();
    return () => { disposed = true; clearTimeout(timer); };
  }, [accept, running, scope, sessionId, turnId]);

  const perform = useCallback(async (id: string, action: () => Promise<SteeringSnapshot | null>) => {
    const key = `${scope}/${id}`;
    if (inFlight.current.has(key)) return false;
    inFlight.current.add(key);
    setOperations(new Set(inFlight.current));
    try {
      const value = await action();
      if (value) accept(value);
      return true;
    } catch (error) {
      if (scopeRef.current === scope) {
        notify(error instanceof Error ? error.message : String(error));
        if (sessionId) void getSteeringQueue(sessionId).then(accept).catch(() => {});
      }
      return false;
    } finally {
      inFlight.current.delete(key);
      setOperations(new Set(inFlight.current));
    }
  }, [accept, notify, scope, sessionId]);

  const currentSnapshot = snapshot?.scope === scope && isSteeringSnapshot(snapshot.value)
    ? snapshot.value : null;
  const messages = useMemo(
    () => currentSnapshot?.messages ?? [],
    [currentSnapshot],
  );
  const pending = useMemo(() => messages.filter((m) => m.status === "queued"), [messages]);
  const delivered = useMemo(() => messages.filter((m) => m.status === "delivered"), [messages]);
  const working = useMemo(() => new Set([...operations]
    .filter((key) => key.startsWith(`${scope}/`))
    .map((key) => key.slice(scope.length + 1))), [operations, scope]);

  return {
    pending,
    delivered,
    working,
    hasSnapshot: currentSnapshot !== null,
    enqueue: (text: string, mode: SteeringMode = "after_tool") => {
      if (!sessionId || !running) return Promise.resolve(false);
      return perform("send", async () => {
        // Verify support before posting: older APIs submit immediately and have no queue UI.
        await getSteeringQueue(sessionId);
        const result = await steerSearch(sessionId, text, mode);
        if (result?.status !== "queued") throw new Error("后端未确认追问已提交，请检查运行记录");
        if (isSteeringSnapshot(result.queue)) return result.queue;
        if (scopeRef.current === scope) {
          notify("追问已提交，但后端未返回队列状态；请勿重复发送，重启 SearchOS API 后可使用队列操作");
        }
        return null;
      });
    },
    guide: (id: string) => sessionId && running
      ? perform(id, () => promoteSteeringMessage(sessionId, id)) : Promise.resolve(false),
    remove: (id: string) => sessionId && running
      ? perform(id, () => removeSteeringMessage(sessionId, id)) : Promise.resolve(false),
  };
}

export type LiveFollowUpController = ReturnType<typeof useLiveFollowUps>;
