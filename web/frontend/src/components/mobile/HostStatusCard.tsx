"use client";
import { RefreshCw, Server } from "lucide-react";
import type { HostConnection } from "@/hooks/useHostStatus";
import { HOST_LABELS, hostMessage, uptimeLabel } from "@/lib/hostStatus";
import s from "./mobile-assistant.module.css";

export default function HostStatusCard({ host }: { host: HostConnection }) {
  const current = host.phase === "online" || host.phase === "degraded";
  const server = ["docker", "systemd"].includes(host.status?.service_manager || "");
  return <section className={s.hostCard} aria-label="主机运行状态">
    <div className={s.hostHeading}><Server size={20} /><b role="status">{HOST_LABELS[host.phase]}</b><button aria-label="刷新主机状态" onClick={host.refresh}><RefreshCw size={17} /></button></div>
    <p>{hostMessage(host)}</p>
    <dl>
      <div><dt>最后响应</dt><dd>{host.lastSeen ? new Date(host.lastSeen).toLocaleTimeString("zh-CN", { hour12: false }) : "尚未收到响应"}</dd></div>
      {current && host.status && <>
        <div><dt>本次连续运行</dt><dd>{uptimeLabel(host.status.uptime_seconds)}</dd></div>
        <div><dt>运行方式</dt><dd>{host.status.service_mode === "managed" ? "系统托管 · 故障重启" : "手动启动"}</dd></div>
        <div><dt>自动启动</dt><dd>{server ? "由服务器服务管理器启动" : host.status.service_mode === "managed" ? "登录电脑后启动" : "尚未配置"}</dd></div>
        {!server && <div><dt>防休眠</dt><dd>{host.status.keep_awake === "ac" ? "已配置接电时保持唤醒" : "未启用"}</dd></div>}
      </>}
    </dl>
    <small>{server ? "任务由服务器执行，手机退出不影响运行。服务自动重启不等于中断的研究任务自动续跑。" : "主机仍需开机联网。合盖、手动休眠或注销账户后，服务可能停止；自动重启不等于研究任务自动续跑。"}</small>
  </section>;
}
