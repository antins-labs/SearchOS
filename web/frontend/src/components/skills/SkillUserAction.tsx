"use client";

import { useState } from "react";
import { respondSkillAction, type SkillCreationJob } from "@/lib/api";

export default function SkillUserAction({ job, zh }: { job: SkillCreationJob; zh: boolean }) {
  const [busy, setBusy] = useState(false);
  const [handled, setHandled] = useState("");
  const [error, setError] = useState("");
  const operation = job.user_action;
  if (job.status !== "waiting_user" || !operation) return null;
  async function respond(action: "open" | "continue" | "skip") {
    if (!operation) return;
    setBusy(true); setError("");
    try {
      await respondSkillAction(job.id, operation.id, action);
      if (action !== "open") setHandled(operation.id);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const disabled = busy || handled === operation.id || operation.state !== "pending";
  return <div className="space-y-2 border-t border-line bg-accent/5 p-4 text-[12px] leading-6" role="status">
    <p className="font-medium text-ink">{zh ? "等待本机浏览器操作" : "Waiting for browser interaction"}</p>
    <p>{operation.message}</p><p className="break-all text-[11px] text-ink-faint">{operation.url}</p>
    <div className="flex flex-wrap gap-2">{(["open", "continue", "skip"] as const).map((action, index) => <button key={action} type="button" disabled={disabled} onClick={() => void respond(action)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-accent-ink disabled:opacity-40">{(zh ? ["打开浏览器", "已完成，继续", "跳过此次操作"] : ["Open browser", "Done, continue", "Skip this action"])[index]}</button>)}</div>
    {handled === operation.id && <p>{zh ? "已记录，等待执行名额…" : "Recorded. Waiting for an execution slot…"}</p>}
    {error && <p role="alert" className="text-err">{error}</p>}
  </div>;
}
