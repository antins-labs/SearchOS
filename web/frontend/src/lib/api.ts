// REST + WebSocket API client

import type {
  EffortLevel,
  EffortView,
  FileNode,
  ModelsView,
  RunDefaultsView,
  SearchRequest,
  SearchResult,
  SettingsData,
  SkillsView,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---- REST ----

export async function getHealth(): Promise<{ status: string; version?: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function startSearch(req: SearchRequest): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);
  return res.json();
}

export async function getSearchResult(sessionId: string): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/api/search/${sessionId}`);
  if (!res.ok) throw new Error(`Get result failed: ${res.statusText}`);
  return res.json();
}

export async function getSearchState(sessionId: string): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/api/search/${sessionId}/state`);
  if (!res.ok) throw new Error(`Get state failed: ${res.statusText}`);
  return res.json();
}

export interface HistoryItem {
  session_id: string;
  title: string;
  status: "running" | "completed" | "incomplete";
  coverage_score: number | null;
  updated_at: number;
}

export async function listHistory(): Promise<HistoryItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/history`, { cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function loadHistory(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/history/${sessionId}`);
  if (!res.ok) throw new Error(`Load session failed: ${res.statusText}`);
  return res.json();
}

export async function renameHistory(sessionId: string, title: string): Promise<void> {
  await fetch(`${API_BASE}/api/history/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteHistory(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/history/${sessionId}`, { method: "DELETE" });
}

export async function getWorkspaceFiles(sessionId: string): Promise<{ tree: FileNode[] }> {
  const res = await fetch(`${API_BASE}/api/workspace/${sessionId}/files`);
  if (!res.ok) throw new Error(`Get files failed: ${res.statusText}`);
  return res.json();
}

export async function getFileContent(sessionId: string, path: string): Promise<{ content: string }> {
  const res = await fetch(`${API_BASE}/api/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`);
  if (!res.ok) throw new Error(`Get file failed: ${res.statusText}`);
  return res.json();
}

// ---- Settings ----

export async function getSettings(): Promise<SettingsData | null> {
  try {
    const res = await fetch(`${API_BASE}/api/settings`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function putJson<T>(path: string, body: unknown, method = "PUT"): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (data.detail?.detail) detail = data.detail.detail;
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json();
}

export const putEffort = (level: EffortLevel, overrides: Record<string, number> = {}) =>
  putJson<EffortView>("/api/settings/effort", { level, overrides });

export const putSkills = (patch: {
  access_only?: string[] | null;
  access_deny?: string[];
  strategy_deny?: string[];
  orchestrator_deny?: string[];
}) => putJson<SkillsView>("/api/settings/skills", patch);

export const patchSkill = (name: string, enabled: boolean) =>
  putJson<SkillsView>(`/api/settings/skills/${encodeURIComponent(name)}`, { enabled }, "PATCH");

export const putSkillCategory = (category: string, enabled: boolean) =>
  putJson<SkillsView>(`/api/settings/skills/category/${encodeURIComponent(category)}`, { enabled });

export const putRoles = (roles: Record<string, string>) =>
  putJson<{ roles: Record<string, string>; role_overrides: Record<string, string>; warnings: string[] }>(
    "/api/settings/models/roles", { roles });

export const putSearchBackend = (provider: string | null) =>
  putJson<ModelsView["search"]>("/api/settings/search-backend", { provider });

export const putMisc = (patch: {
  max_time_s?: number;
  search_max_results?: number;
  enable_skills?: boolean;
  browser_backend?: string;
}) => putJson<RunDefaultsView & { browser_backend: string }>("/api/settings/misc", patch);

export const resetSettings = () =>
  putJson<SettingsData>("/api/settings/reset", {}, "POST");

// ---- WebSocket ----

export function connectWebSocket(
  sessionId: string,
  onMessage: (event: Record<string, unknown>) => void,
  onClose?: () => void,
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/api/ws/${sessionId}`);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onMessage(data);
    } catch {
      // ignore parse errors
    }
  };

  ws.onclose = () => onClose?.();
  ws.onerror = () => onClose?.();

  return ws;
}
