export interface HostStatus {
  scheduler_running: boolean;
  last_tick: number;
  server_time: number;
  started_at: number;
  uptime_seconds: number;
  instance_id: string;
  service_mode: "managed" | "manual";
  service_manager?: string;
  keep_awake: "ac" | "off";
  catchup_window_minutes: number;
  push_ready: boolean;
  push_reason: string;
}
export interface HostSnapshot {
  phase: "checking" | "online" | "degraded" | "unreachable";
  status: HostStatus | null;
  lastSeen: number | null;
  notice: "reconnected" | "restarted" | null;
  noticeAt: number;
}
export const INITIAL_HOST: HostSnapshot = { phase: "checking", status: null, lastSeen: null, notice: null, noticeAt: 0 };
export const HOST_STALE_MS = 25000;
export function receivedHost(previous: HostSnapshot, status: HostStatus, now: number): HostSnapshot {
  const restarted = previous.status && previous.status.instance_id !== status.instance_id;
  const reconnected = previous.lastSeen !== null && ["checking", "unreachable"].includes(previous.phase);
  return {
    phase: status.scheduler_running ? "online" : "degraded", status, lastSeen: now,
    notice: restarted ? "restarted" : reconnected ? "reconnected" : previous.notice,
    noticeAt: restarted || reconnected ? now : previous.noticeAt,
  };
}
export function freshHost(previous: HostSnapshot, now: number): HostSnapshot {
  if (previous.lastSeen !== null && now - previous.lastSeen > HOST_STALE_MS && ["online", "degraded"].includes(previous.phase)) {
    return { ...previous, phase: "checking" };
  }
  return previous;
}
export const HOST_LABELS = { checking: "检查连接", online: "主机在线", degraded: "计划异常", unreachable: "连接中断" };
export function hostMessage(host: HostSnapshot): string {
  if (host.phase === "unreachable") return "暂时无法连接主机，请检查网络和主机服务。恢复后自动更新。";
  if (host.phase === "checking") return "正在检查主机状态…";
  if (host.phase === "degraded") return "计划服务响应异常，定时任务可能延迟。";
  return "计划服务正常，退出页面后任务继续运行。";
}
export function uptimeLabel(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  if (!minutes) return "不足 1 分钟";
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} 小时 ${minutes % 60} 分钟` : `${Math.floor(hours / 24)} 天 ${hours % 24} 小时`;
}
