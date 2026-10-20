"use client";

import { useEffect, useState } from "react";
import { getSkillGeneration } from "@/lib/api";
import type { SkillGeneration } from "@/lib/types";

/** 后台生成独立于搜索连接；使用本轮 ID 轮询，终态停止，切换会话撤销请求。 */
export function useSkillGeneration(sessionId: string | null, generationId?: string | null) {
  const key = sessionId && generationId ? `${sessionId}/${generationId}` : "";
  const [snapshot, setSnapshot] = useState<{ key: string; data: SkillGeneration | null; error: string }>({ key: "", data: null, error: "" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!sessionId || !generationId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    async function refresh() {
      try {
        const data = await getSkillGeneration(sessionId!, generationId!, controller.signal);
        if (disposed) return;
        setSnapshot({ key, data, error: "" });
        if (data.status === "queued" || data.status === "running") timer = setTimeout(refresh, 2000);
      } catch (error) {
        if (disposed) return;
        setSnapshot((previous) => ({ key, data: previous.key === key ? previous.data : null,
          error: error instanceof Error ? error.message : String(error) }));
        timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { disposed = true; controller.abort(); if (timer) clearTimeout(timer); };
  }, [sessionId, generationId, key, attempt]);

  return {
    data: snapshot.key === key ? snapshot.data : null,
    error: snapshot.key === key ? snapshot.error : "",
    retry: () => setAttempt((value) => value + 1),
  };
}
