"use client";

import { useState } from "react";
import { clearSkillBrowserSession, listSkillBrowserSessions, type SkillBrowserSession } from "@/lib/api";

export default function SkillBrowserSessions({ zh }: { zh: boolean }) {
  const [items, setItems] = useState<SkillBrowserSession[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(site?: string) {
    setBusy(true); setError("");
    try {
      if (site) await clearSkillBrowserSession(site);
      setItems(await listSkillBrowserSessions());
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <details className="mt-6 border-t border-line pt-4 text-[12px] text-ink-dim" onToggle={(e) => { if (e.currentTarget.open) void load(); }}>
    <summary className="cursor-pointer">{zh ? "本机站点会话" : "Local site sessions"}</summary>
    <p className="my-2 text-[11px] text-ink-faint">{zh ? "清除后，该站点下次访问可能需要重新登录。占用中的会话须等任务结束后清除。" : "Clearing a session may require login on the next visit. Active sessions can be cleared after the task ends."}</p>
    {error && <p role="alert" className="text-err">{error}</p>}
    {items.map((item) => <div key={item.site} className="flex items-center justify-between gap-2 py-1"><span>{item.site}{item.busy ? (zh ? " · 使用中" : " · In use") : ""}</span><button type="button" disabled={busy || item.busy} onClick={() => void load(item.site)} className="rounded border border-line px-2 py-1 disabled:opacity-40">{zh ? "清除会话" : "Clear session"}</button></div>)}
    {!items.length && !busy && <p>{zh ? "暂无保存的站点会话" : "No saved sessions"}</p>}
  </details>;
}
