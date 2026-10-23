"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { assistant, dateLabel, runLabels, type Access, type Inbox, type Plan, type Preferences, type PushConfig, type Report, type Run } from "@/lib/assistant";
import { CalendarClock, ChevronRight } from "lucide-react";
import MobileReport from "./MobileReport";
import MobileSheet from "./MobileSheet";
import HostStatusCard from "./HostStatusCard";
import type { HostConnection } from "@/hooks/useHostStatus";
import s from "./mobile-assistant.module.css";
const errorText = (e: unknown) => e instanceof Error ? e.message : "操作失败，请重试";
const pushReasonLabels: Record<string, string> = {
  "需要先配置 HTTPS 访问入口": "请先配置 HTTPS 远程地址。",
  "服务端尚未配置 SF_PUSH_CONTACT 联系邮箱": "请联系管理员配置通知服务。",
  "服务端尚未安装 mobile 推送依赖": "请联系管理员安装通知服务。",
};
export function useAssistant() {
  const [plans, setPlans] = useState<Plan[]>([]); const [inbox, setInbox] = useState<Inbox>({ items: [], unread: 0 });
  const [error, setError] = useState("");
  const refresh = useCallback(async () => { try { const [plans, inbox] = await Promise.all([assistant<Plan[]>("/schedules"), assistant<Inbox>("/inbox")]); setPlans(plans); setInbox(inbox); setError(""); } catch (e) { setError(errorText(e)); } }, []);
  useEffect(() => { void Promise.resolve().then(refresh); const timer = setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 10000); const visible = () => { if (document.visibilityState === "visible") void refresh(); }; document.addEventListener("visibilitychange", visible); return () => { clearInterval(timer); document.removeEventListener("visibilitychange", visible); }; }, [refresh]);
  return { plans, inbox, error, refresh };
}
export function PlanCard({ plan, onEdit, refresh, onTarget }: { plan: Plan; onEdit: () => void; refresh: () => Promise<void>; onTarget: (url: string) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [runs, setRuns] = useState<Run[] | null>(null);
  const runKey = useRef(crypto.randomUUID());
  const act = async (action: string) => { if (busy) return; if ((action === "delete" || action === "run-now") && !window.confirm(action === "delete" ? "删除计划？已生成的报告会保留。" : "立即执行一次？将产生模型用量。")) return; setBusy(true); setError(""); try { await assistant(`/schedules/${plan.id}/${action}`, "POST", { version: plan.version }, runKey.current); runKey.current = crypto.randomUUID(); await refresh(); setRuns(await assistant<Run[]>(`/schedules/${plan.id}/runs`)); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } };
  useEffect(() => { if (!runs?.some(run => ["queued", "running"].includes(run.status))) return; const timer = setInterval(() => { void assistant<Run[]>(`/schedules/${plan.id}/runs`).then(setRuns).catch(e => setError(errorText(e))); }, 4000); return () => clearInterval(timer); }, [runs, plan.id]);
  return <article className={s.planCard}>
    <div className={s.planTop}><span className={s.tileIcon}><CalendarClock size={20} /></span><button className={s.switch} role="switch" aria-checked={plan.active} aria-label={`${plan.active ? "暂停" : "启用"}${plan.title}`} disabled={busy} onClick={() => void act(plan.active ? "pause" : "resume")}><span /></button></div>
    <button className={s.planTitle} onClick={onEdit}><h3>{plan.title}</h3><ChevronRight size={17} /></button>
    <div className={s.planTime}>{plan.time}<span>{plan.frequency === "daily" ? "每天" : plan.frequency === "weekly" ? `每周${["一","二","三","四","五","六","日"][plan.weekday-1]}` : plan.date}</span></div>
    <p className={s.planNext}>{plan.active ? plan.next_run ? `下次 ${dateLabel(plan.next_run)}` : "等待执行" : "已暂停"} · {plan.timezone}</p>
    <div className={s.planFooter}><button disabled={busy} onClick={() => { if (runs) setRuns(null); else void assistant<Run[]>(`/schedules/${plan.id}/runs`).then(setRuns).catch(e => setError(errorText(e))); }}>执行记录<ChevronRight size={14} /></button><details><summary>管理</summary><div className={s.cardButtons}><button disabled={busy} onClick={onEdit}>编辑</button><button disabled={busy} onClick={() => void act("run-now")}>立即执行</button><button disabled={busy} onClick={() => void act("delete")}>删除</button></div></details></div>
    {error && <p className={s.error} role="alert">{error}</p>}{runs && <div>{!runs.length && <p className={s.caption}>暂无执行记录</p>}{runs.map(run => <button key={run.id} className={s.messageCard} disabled={!run.report_id && !run.session_id} onClick={() => onTarget(run.report_id ? `/m?report=${run.report_id}` : `/m?session=${run.session_id}`)}><b>{runLabels[run.status] || run.status}</b><small>{dateLabel(run.created)}</small>{run.error && <p>{run.error}</p>}</button>)}{runs.length >= 50 && <button className={s.textButton} onClick={() => void assistant<Run[]>(`/schedules/${plan.id}/runs?before=${runs[runs.length-1].created}`).then(more => setRuns([...runs, ...more])).catch(e => setError(errorText(e)))}>加载更早记录</button>}</div>}
  </article>;
}
export function InboxPanel({ inbox, refresh, onTarget, onClose }: { inbox: Inbox; refresh: () => Promise<void>; onTarget: (url: string) => void; onClose: () => void }) {
  const [older, setOlder] = useState<Inbox["items"]>([]); const [error, setError] = useState(""); const [more, setMore] = useState(true);
  const items = [...inbox.items, ...older.filter(item => !inbox.items.some(current => current.id === item.id))];
  return <MobileSheet title="消息中心" subtitle={`${inbox.unread} 条未读`} onClose={onClose}>
    {!items.length && <div className={s.empty}><h3>暂无消息</h3><p>任务完成或异常时会在此提醒。</p></div>}
    {items.map(item => <button key={item.id} className={s.messageCard} data-unread={!item.read_at} onClick={async () => { try { await assistant(`/inbox/${item.id}/read`, "POST"); await refresh(); onClose(); onTarget(item.url); } catch (e) { setError(errorText(e)); } }}><b>{item.title}</b><p>{item.body}</p><small>{dateLabel(item.created)} · {item.read_at ? "已读" : "未读"}</small></button>)}
    {items.length >= 50 && more && <button className={s.outlineButton} onClick={async () => { try { const next = await assistant<Inbox>(`/inbox?before=${items[items.length-1].created}`); setOlder([...older, ...next.items]); setMore(next.items.length === 50); } catch (e) { setError(errorText(e)); } }}>更早的消息</button>}{error && <p className={s.error}>{error}</p>}
  </MobileSheet>;
}
export function ReportPanel({ id, onClose, onOpen, onSource }: { id: string; onClose: () => void; onOpen: (id: string) => void; onSource: (ref: string) => void }) {
  const [report, setReport] = useState<Report | null>(null); const [error, setError] = useState("");
  useEffect(() => { let alive = true; void assistant<Report>(`/reports/${encodeURIComponent(id)}`).then(value => { if (alive) setReport(value); }).catch(e => { if (alive) setError(errorText(e)); }); return () => { alive = false; }; }, [id]);
  return <MobileSheet title="任务报告" subtitle={report ? dateLabel(report.created) : "正在读取…"} onClose={onClose} footer={report && <button className={s.primaryButton} onClick={() => { onClose(); onOpen(report.session_id); }}>继续追问</button>}>
    {error && <p className={s.error} role="alert">{error}</p>}{report && <MobileReport query={report.query} answer={report.answer || "暂无正文，请打开任务查看。"} searchState={report.search_state} inlineReader onSource={source => { onClose(); onSource(source); }} onContinue={() => { onClose(); onOpen(report.session_id); }} />}

  </MobileSheet>;
}
interface Device { id: string; name: string; admin: boolean; last_seen: number; expires: number; revoked: number | null }
export function ConnectionPanel({ onClose, host }: { onClose: () => void; host: HostConnection }) {
  const [access, setAccess] = useState<Access | null>(null); const [devices, setDevices] = useState<Device[]>([]); const [pair, setPair] = useState<{ code: string; expires: number; url: string } | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { try { const [a, d] = await Promise.all([assistant<Access>("/access"), assistant<Device[]>("/devices")]); setAccess(a); setDevices(d); } catch (e) { setError(errorText(e)); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return <MobileSheet title="连接与设备" onClose={onClose}><HostStatusCard host={host} /><div className={s.connectionDetail}><h3>{access ? access.remote ? "远程地址" : "本机连接" : "正在连接…"}</h3><p>{access?.origin || "当前连接本机服务"}</p></div>
    {access && !access.remote && <div className={s.notice}><p><b>仅限本机访问</b><span>配置 HTTPS 远程地址后，可登录和配对手机。</span></p></div>}
    {access?.remote && access.device?.admin && <><button className={s.primaryButton} disabled={busy} onClick={async () => { setBusy(true); try { setPair(await assistant("/pairings", "POST")); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }}>生成配对码</button>{pair && <div className={s.messageCard}><div className={s.pairCode}>{pair.code}</div><p>在手机打开 {pair.url} 并输入配对码，即可访问整个个人工作区。</p><small>有效至 {dateLabel(pair.expires)} · 仅可使用一次</small></div>}</>}
    {devices.filter(d => !d.revoked).map(device => <div key={device.id} className={s.messageCard}><b>{device.name}{device.id === access?.device?.id ? " · 当前设备" : ""}</b><p>{device.admin ? "管理员" : "个人设备"} · 最近使用 {dateLabel(device.last_seen)}</p><small>登录有效至 {dateLabel(device.expires)}</small><button className={s.textButton} disabled={busy} onClick={async () => { if (!window.confirm(`撤销“${device.name}”的访问权限？`)) return; setBusy(true); try { await assistant(`/devices/${device.id}`, "DELETE"); if (device.id === access?.device?.id) window.location.reload(); else await refresh(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }}>撤销访问</button></div>)}
    {error && <p role="alert" className={s.error}>{error}</p>}
  </MobileSheet>;
}
export function NotificationsPanel({ onClose }: { onClose: () => void }) {
  const [config, setConfig] = useState<PushConfig | null>(null); const [prefs, setPrefs] = useState<Preferences | null>(null); const [worker, setWorker] = useState<ServiceWorkerRegistration | null>(null); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { const [config, prefs] = await Promise.all([assistant<PushConfig>("/push/config"), assistant<Preferences>("/preferences")]); setConfig(config); setPrefs(prefs); }, []);
  useEffect(() => { void load().catch(e => setError(errorText(e))); if ("serviceWorker" in navigator && window.isSecureContext) void navigator.serviceWorker.register("/searchos-sw.js", { scope: "/m" }).then(() => navigator.serviceWorker.ready).then(setWorker).catch(e => setError(errorText(e))); }, [load]);
  const enable = async () => {
    if (!config?.ready || !worker || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      // Permission request must originate directly in the user's tap (iOS).
      const permission = await Notification.requestPermission();
      if (permission !== "granted") throw new Error("请在系统设置中允许通知。");
      const bytes = Uint8Array.from(atob(config.public_key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - config.public_key.length % 4) % 4)), char => char.charCodeAt(0));
      const existing = await worker.pushManager.getSubscription();
      const sub = existing || await worker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes });
      try { await assistant("/push/subscriptions", "POST", sub.toJSON()); } catch (e) { if (!existing) await sub.unsubscribe(); throw e; }
      await load(); setNotice("通知已开启。");
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const supported = typeof window !== "undefined" && "Notification" in window && "PushManager" in window;
  return <MobileSheet title="通知与提醒" onClose={onClose}>
    <div className={s.notice}><p><b>{config?.ready ? "通知服务已就绪" : "通知服务未配置"}</b><span>{(config?.reason && pushReasonLabels[config.reason]) || config?.reason || "通知仅包含任务状态。"}</span></p></div>
    <p className={s.caption}>iPhone：用 Safari 打开 HTTPS 地址，添加到主屏幕后，从主屏幕开启通知。</p>
    <button className={s.primaryButton} disabled={!supported || !worker || !config?.ready || busy} onClick={() => void enable()}>{config?.subscriptions.length ? "同步设备通知" : "开启通知"}</button>
    {!supported && <p className={s.caption}>当前浏览器不支持通知，可在消息中心查看。</p>}
    {!!config?.subscriptions.length && <div className={s.cardButtons}><button disabled={busy} onClick={async () => { setBusy(true); try { await assistant("/push/test", "POST"); setNotice("测试通知已排队，请稍后刷新状态。"); await load(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }}>发送测试通知</button><button disabled={busy} onClick={async () => { setBusy(true); try { await assistant("/push/subscriptions", "DELETE"); const sub = await worker?.pushManager.getSubscription(); await sub?.unsubscribe(); await load(); setNotice("此设备通知已关闭。"); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }}>关闭设备通知</button></div>}
    {prefs && <><label className={s.toggleRow}><span>任务完成提醒</span><input type="checkbox" checked={prefs.completed} onChange={e => setPrefs({ ...prefs, completed: e.target.checked })} /></label><label className={s.toggleRow}><span>任务异常提醒</span><input type="checkbox" checked={prefs.errors} onChange={e => setPrefs({ ...prefs, errors: e.target.checked })} /></label><label className={s.toggleRow}><span>免打扰</span><input type="checkbox" checked={prefs.quiet_enabled} onChange={e => setPrefs({ ...prefs, quiet_enabled: e.target.checked })} /></label>
    {prefs.quiet_enabled && <><div className={s.formGrid}><label className={s.fieldLabel}>开始<input type="time" value={prefs.quiet_start} onChange={e => setPrefs({ ...prefs, quiet_start: e.target.value })} /></label><label className={s.fieldLabel}>结束<input type="time" value={prefs.quiet_end} onChange={e => setPrefs({ ...prefs, quiet_end: e.target.value })} /></label></div><label className={s.fieldLabel}>免打扰时区<input value={prefs.timezone} onChange={e => setPrefs({ ...prefs, timezone: e.target.value })} /></label><p className={s.caption}>免打扰结束后发送通知，消息可随时查看。</p></>}
    <button className={s.outlineButton} disabled={busy} onClick={async () => { setBusy(true); try { await assistant("/preferences", "PUT", prefs); setNotice("设置已保存。"); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }}>保存设置</button></>}
    {config && config.deliveries.length > 0 && <div className={s.messageCard}><b>发送记录</b>{config.deliveries.map((item, index) => <p key={index}>{{ sent: "已提交推送", pending: "待发送", sending: "发送中", failed: "发送失败", expired: "设备通知已失效", cancelled: "已取消" }[item.status] || item.status} · 尝试 {item.attempts} 次 {item.error}</p>)}<button className={s.textButton} onClick={() => void load().catch(e => setError(errorText(e)))}>刷新状态</button></div>}
    {notice && <p role="status" className={s.caption}>{notice}</p>}{error && <p role="alert" className={s.error}>{error}</p>}
  </MobileSheet>;
}
