"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "@/lib/api";
import { freshHost, INITIAL_HOST, receivedHost, type HostStatus } from "@/lib/hostStatus";

export function useHostStatus() {
  const [host, setHost] = useState(INITIAL_HOST);
  const refreshRef = useRef<() => void>(() => undefined);
  useEffect(() => {
    let alive = true;
    let pending: AbortController | null = null;
    let nextCheck = 0;
    const check = async () => {
      if (!alive) return;
      setHost(current => freshHost(current, Date.now()));
      if (!navigator.onLine) {
        pending?.abort(); pending = null;
        setHost(current => ({ ...current, phase: "unreachable" }));
        return;
      }
      if (pending) return;
      const controller = new AbortController();
      pending = controller;
      try {
        const status = await request<HostStatus>("/api/assistant/status", { cache: "no-store", signal: controller.signal }, { timeoutMs: 6000 });
        if (alive && !controller.signal.aborted) setHost(current => receivedHost(current, status, Date.now()));
      } catch {
        if (alive && !controller.signal.aborted) setHost(current => ({ ...current, phase: "unreachable" }));
      } finally {
        if (pending === controller) { pending = null; nextCheck = Date.now() + 10000; }
      }
    };
    const visible = () => { if (document.visibilityState === "visible") void check(); };
    const network = () => { void check(); };
    refreshRef.current = () => { void check(); };
    void Promise.resolve().then(check);
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      setHost(current => freshHost(current, Date.now()));
      if (Date.now() >= nextCheck) void check();
    }, 1000);
    window.addEventListener("online", network);
    window.addEventListener("offline", network);
    document.addEventListener("visibilitychange", visible);
    return () => {
      alive = false; pending?.abort(); clearInterval(timer);
      window.removeEventListener("online", network);
      window.removeEventListener("offline", network);
      document.removeEventListener("visibilitychange", visible);
      refreshRef.current = () => undefined;
    };
  }, []);
  const refresh = useCallback(() => refreshRef.current(), []);
  return { ...host, refresh };
}
export type HostConnection = ReturnType<typeof useHostStatus>;
