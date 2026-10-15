import { request } from "./api";
import type { SourceSelection, SearchState } from "./types";
export interface Plan { id: string; version: number; title: string; instruction: string; frequency: "daily" | "weekly" | "once"; time: string; weekday: number; date: string | null; timezone: string; effort: "low" | "medium" | "high" | "max"; max_time: number; sources: SourceSelection; active: boolean; next_run: number | null }
export type PlanInput = Omit<Plan, "id" | "next_run" | "version"> & { version?: number };
export interface Access { remote: boolean; authenticated: boolean; device: { id: string; name: string; admin: boolean } | null; origin: string | null }
export interface Message { id: string; title: string; body: string; url: string; created: number; read_at: number | null; kind: string }
export interface Inbox { items: Message[]; unread: number }
export interface Run { id: string; status: string; created: number; session_id: string | null; report_id: string | null; error: string }
export interface Report { id: string; created: number; session_id: string; query: string; answer: string; search_state: SearchState | null }
export interface Preferences { completed: boolean; errors: boolean; quiet_enabled: boolean; quiet_start: string; quiet_end: string; timezone: string }
export interface PushConfig { ready: boolean; reason: string; public_key: string; subscriptions: { id: string }[]; deliveries: { status: string; attempts: number; error: string }[] }
export function assistant<T>(path: string, method = "GET", body?: unknown, key?: string): Promise<T> {
  return request<T>(`/api/assistant${path}`, { method, cache: "no-store", headers: { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
}
export const dateLabel = (stamp: number) => new Date(stamp * 1000).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
export const runLabels: Record<string, string> = { queued: "等待执行", running: "进行中", completed: "已完成", error: "执行失败", interrupted: "已中断", skipped: "已跳过" };
