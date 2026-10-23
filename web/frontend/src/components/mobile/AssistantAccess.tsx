"use client";
import Image from "next/image";
import { useEffect, useState, type ReactNode } from "react";
import { assistant, type Access } from "@/lib/assistant";
import s from "./mobile-assistant.module.css";
export default function AssistantAccess({ children }: { children: ReactNode }) {
  const [access, setAccess] = useState<Access | null>(null); const [error, setError] = useState(""); const [admin, setAdmin] = useState(false); const [value, setValue] = useState(""); const [name, setName] = useState("我的 iPhone"); const [busy, setBusy] = useState(false);
  useEffect(() => { const check = () => { void assistant<Access>("/access").then(setAccess).catch(e => setError(e.message)); }; check(); window.addEventListener("searchos:unauthorized", check); return () => window.removeEventListener("searchos:unauthorized", check); }, []);
  if (access?.authenticated) return children;
  return <div className={s.app}><main className={s.page}><Image unoptimized src="/searchos-mark.png" alt="SearchOS" className={s.accessMark} width={58} height={58} /><h1 className={s.accessTitle}>连接助理</h1><p className={s.caption}>{access ? access.remote ? "输入管理员设备生成的配对码，即可访问个人工作区。" : "当前仅限本机访问，请先配置 HTTPS 远程地址。" : "正在检查连接…"}</p>
    {access?.remote && <form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try { await assistant(admin ? "/login" : "/pairings/claim", "POST", { [admin ? "token" : "code"]: value.trim(), name }); window.location.reload(); } catch (e) { setError(e instanceof Error ? e.message : "连接失败"); } finally { setBusy(false); } }}>
      <label className={s.fieldLabel}>设备名称<input value={name} maxLength={80} required onChange={e => setName(e.target.value)} /></label><label className={s.fieldLabel}>{admin ? "管理员凭据" : "8 位配对码"}<input type={admin ? "password" : "text"} autoComplete="off" inputMode={admin ? "text" : "numeric"} value={value} required onChange={e => setValue(e.target.value)} /></label>
      <button className={s.primaryButton} disabled={busy}>{busy ? "正在连接…" : "连接 SearchOS"}</button><button className={s.textButton} type="button" onClick={() => { setAdmin(!admin); setValue(""); }}>{admin ? "用配对码绑定" : "管理员登录"}</button>
      {admin && <p className={s.caption}>使用服务端 admin-token 中的凭据登录，再到“我的 → 更多设置”配置模型和搜索。</p>}
    </form>}
    {error && <p role="alert" className={s.error}>{error}</p>}<button className={s.textButton} onClick={() => window.location.reload()}>重试连接</button></main></div>;
}
