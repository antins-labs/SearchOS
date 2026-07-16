// REST + WebSocket API client

import type {
  AdvancedView,
  BrowserDiagnostic,
  EffortLevel,
  EffortView,
  FileNode,
  ModelsView,
  ProvidersResponse,
  ProviderDiagnostic,
  RepairRequest,
  ResolveEvidenceRequest,
  ResolveEvidenceResponse,
  RunDefaultsView,
  SearchRequest,
  SearchDiagnostic,
  SearchResult,
  SearchState,
  SettingsData,
  SkillsView,
  WSEvent,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 12000;

function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => {
      controller.abort();
      reject(new Error("Request timed out"));
    }, timeoutMs);

    fetch(input, { ...init, signal: init.signal ?? controller.signal }).then(
      (response) => {
        globalThis.clearTimeout(timeout);
        resolve(response);
      },
      (error) => {
        globalThis.clearTimeout(timeout);
        reject(error);
      },
    );
  });
}

function readJsonWithTimeout<T>(response: Response): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => reject(new Error("Response timed out")), REQUEST_TIMEOUT_MS);
    response.json().then(
      (data) => {
        globalThis.clearTimeout(timeout);
        resolve(data as T);
      },
      (error) => {
        globalThis.clearTimeout(timeout);
        reject(error);
      },
    );
  });
}

// ---- REST ----

export async function getHealth(): Promise<{ status: string; version?: string } | null> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return readJsonWithTimeout(res);
  } catch {
    return null;
  }
}

export async function startSearch(req: SearchRequest): Promise<{ session_id: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
}

export async function startRepair(
  sessionId: string,
  req: RepairRequest,
): Promise<RepairStartResponse> {
  const res = await fetchWithTimeout(
    `${API_BASE}/api/search/${sessionId}/repair`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
    35000,
  );
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await readJsonWithTimeout<{ detail?: string | string[] }>(res);
      if (Array.isArray(body.detail)) detail = body.detail.join("; ");
      else if (body.detail) detail = body.detail;
    } catch { /* keep statusText */ }
    if (res.status === 404 && detail === "Not Found") {
      throw new Error("Repair API unavailable — restart the SearchOS API to load the current WebUI routes");
    }
    throw new Error(`Repair failed: ${detail}`);
  }
  return readJsonWithTimeout(res);
}

export interface RepairStartResponse {
  session_id: string;
  task_ids: string[];
  planner: "orchestrator" | "llm" | "deterministic";
  planning_latency_ms: number;
  planning_warning?: string | null;
}

export async function resolveEvidence(
  sessionId: string,
  req: ResolveEvidenceRequest,
): Promise<ResolveEvidenceResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search/${sessionId}/evidence/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await readJsonWithTimeout<{ detail?: string }>(res);
      if (body.detail) detail = body.detail;
    } catch { /* keep statusText */ }
    throw new Error(`Resolve evidence failed: ${detail}`);
  }
  return readJsonWithTimeout(res);
}

export async function stopSearch(sessionId: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search/${sessionId}/stop`, { method: "POST" });
  if (!res.ok) throw new Error(`Stop failed: ${res.statusText}`);
}

export async function steerSearch(sessionId: string, message: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search/${sessionId}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Steer failed: ${res.statusText}`);
}

export async function getSearchResult(sessionId: string): Promise<SearchResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search/${sessionId}`);
  if (!res.ok) throw new Error(`Get result failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
}

export async function getSearchState(sessionId: string): Promise<SearchResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/search/${sessionId}/state`);
  if (!res.ok) throw new Error(`Get state failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
}

export interface HistoryItem {
  session_id: string;
  title: string;
  status: "running" | "completed" | "incomplete" | "error";
  coverage_score: number | null;
  updated_at: number;
  project: string;
  tags: string[];
  favorite: boolean;
  archived: boolean;
}

export interface HistoryAssetPatch {
  title?: string;
  project?: string;
  tags?: string[];
  favorite?: boolean;
  archived?: boolean;
}

export type HistoryStateSource = "snapshot" | "latest" | "unavailable";

export interface HistoryTurn {
  query: string;
  answer: string;
  steers?: string[];
  search_state: SearchState | null;
  state_source: HistoryStateSource;
  coverage_score: number | null;
  evidence_count: number | null;
  completed_at?: string | null;
  elapsed_s?: number | null;
  total_queries?: number | null;
  total_steps?: number | null;
  tool_counts?: SearchResult["tool_counts"] | null;
  token_usage?: SearchResult["token_usage"] | null;
  token_phases?: SearchResult["token_phases"] | null;
  model_distribution?: SearchResult["model_distribution"] | null;
}

export interface HistoryDetail {
  session_id: string;
  query: string;
  status: "running" | "completed" | "incomplete";
  turns: HistoryTurn[];
  coverage_score: number | null;
  evidence_count: number | null;
  answer: string;
  search_state: SearchState | null;
  events: WSEvent[];
}

export async function listHistory(query = ""): Promise<HistoryItem[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  const suffix = params.size ? `?${params.toString()}` : "";
  const res = await fetchWithTimeout(`${API_BASE}/api/history${suffix}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Load history failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
}

export async function loadHistory(sessionId: string): Promise<HistoryDetail> {
  const res = await fetchWithTimeout(`${API_BASE}/api/history/${sessionId}`);
  if (!res.ok) throw new Error(`Load session failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
}

export interface HistoryBranchResponse {
  session_id: string;
  source_session_id: string;
  source_turn_index: number;
  status: "ready";
}

export async function branchHistoryTurn(sessionId: string, turnIndex: number): Promise<HistoryBranchResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/history/${sessionId}/turns/${turnIndex}/branch`, {
    method: "POST",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await readJsonWithTimeout<{ detail?: string }>(res);
      if (body.detail) detail = body.detail;
    } catch { /* keep statusText */ }
    throw new Error(`Create branch failed: ${detail}`);
  }
  return readJsonWithTimeout(res);
}

export async function renameHistory(sessionId: string, title: string): Promise<void> {
  await updateHistoryAssets(sessionId, { title });
}

export async function updateHistoryAssets(
  sessionId: string,
  patch: HistoryAssetPatch,
): Promise<HistoryAssetPatch & { session_id: string; title: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/history/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await readJsonWithTimeout<{ detail?: string }>(res);
      if (body.detail) detail = body.detail;
    } catch { /* keep statusText */ }
    throw new Error(`Update failed: ${detail}`);
  }
  return readJsonWithTimeout(res);
}

export async function deleteHistory(sessionId: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_BASE}/api/history/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete failed: ${res.statusText}`);
}

export async function getWorkspaceFiles(sessionId: string): Promise<{ tree: FileNode[] }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/workspace/${sessionId}/files`);
  if (!res.ok) throw new Error(`Get files failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
}

export async function getFileContent(sessionId: string, path: string): Promise<{ content: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`);
  if (!res.ok) throw new Error(`Get file failed: ${res.statusText}`);
  return readJsonWithTimeout(res);
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
  enable_access_skill_generation?: boolean | null;
  access_skill_max_per_run?: number | null;
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
  enable_explore_batch?: boolean;
  browser_backend?: string;
}) => putJson<RunDefaultsView & { browser_backend: string }>("/api/settings/misc", patch);

// First-class runtime knobs. Only keys present in the patch are touched; send
// null to clear a knob back to its env/code default. https_proxy "" forces
// no-proxy. Proxy / cache dir are not secrets.
export const putAdvanced = (patch: {
  llm_max_retries?: number | null;
  orch_coverage_stall_rounds?: number | null;
  browser_disk_cache_dir?: string | null;
  https_proxy?: string | null;
  search_max_results?: number | null;
  use_layered_context?: boolean | null;
}) => putJson<AdvancedView>("/api/settings/advanced", patch);

export const resetSettings = () =>
  putJson<SettingsData>("/api/settings/reset", {}, "POST");

// Throws on failure (unlike getSettings): the provider switcher shows an
// inline retry row and needs to distinguish errors from empty data.
export async function getProviderPresets(): Promise<ProvidersResponse> {
  const res = await fetch(`${API_BASE}/api/settings/providers`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Couldn't load presets: ${res.statusText}`);
  return res.json();
}

export const putSettingsKey = (env: string, value: string) =>
  putJson<ModelsView>("/api/settings/keys", { env, value });

// Create/update a user-defined provider connection (referenced by model cards).
export const putProviderConnection = (name: string, body: {
  protocol?: "openai_compatible" | "openai" | "anthropic";
  api_base?: string;
  api_key_envs: string[];
  thinking_style?: "chat_template_kwargs" | "enable_thinking" | "none";
  label?: string;
}) => putJson<ModelsView>(`/api/settings/provider-connections/${encodeURIComponent(name)}`, body);

export const deleteProviderConnection = (name: string) =>
  putJson<ModelsView>(`/api/settings/provider-connections/${encodeURIComponent(name)}`, {}, "DELETE");

// Model-card edits. provider_ref repoints the card at a provider connection;
// the card then only carries model id + temperature + enable_thinking. On a base
// profile "" clears a connection-field override; send null to clear temperature/
// provider_ref, omit a field to leave it unchanged.
export const patchProfile = (name: string, patch: {
  model?: string;
  api_base?: string;
  api_key_env?: string;
  provider?: "openai_compatible" | "openai" | "anthropic";
  provider_ref?: string | null;
  temperature?: number | null;
  enable_thinking?: boolean;
  thinking_style?: "chat_template_kwargs" | "enable_thinking" | "none";
  rpm?: number | null;
  tpm?: number | null;
}) => putJson<ModelsView>(`/api/settings/profiles/${encodeURIComponent(name)}`, patch, "PATCH");

export const createProfile = (body: {
  name: string;
  model: string;
  provider_ref?: string | null;
  provider?: string;
  api_base?: string;
  api_key_env?: string;
  temperature?: number | null;
  enable_thinking?: boolean;
  thinking_style?: "chat_template_kwargs" | "enable_thinking" | "none";
  rpm?: number;
  tpm?: number;
}) => putJson<ModelsView>("/api/settings/profiles", body, "POST");

export const deleteProfile = (name: string) =>
  putJson<ModelsView>(`/api/settings/profiles/${encodeURIComponent(name)}`, {}, "DELETE");

async function runDiagnostic<T>(path: string, body: unknown): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 65000);
  try {
    const res = await fetch(`${API_BASE}/api/diagnostics/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`Diagnostic failed: ${res.statusText}`);
    return await res.json() as T;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export const testProvider = (role: string) =>
  runDiagnostic<ProviderDiagnostic>("provider", { role });

export const testSearchBackend = (query: string) =>
  runDiagnostic<SearchDiagnostic>("search", { query });

export const testBrowserBackend = (url: string) =>
  runDiagnostic<BrowserDiagnostic>("browser", { url });

// ---- WebSocket ----

export function connectWebSocket(
  sessionId: string,
  onMessage: (event: Record<string, unknown>) => void,
  onClose?: () => void,
  opts?: { tail?: boolean; onOpen?: () => void },
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/api/ws/${sessionId}${opts?.tail ? "?tail=1" : ""}`);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onMessage(data);
    } catch {
      // ignore parse errors
    }
  };

  ws.onopen = () => opts?.onOpen?.();
  ws.onclose = () => onClose?.();
  // Browsers dispatch `close` after an errored connection is closed. Keeping
  // recovery on that single path prevents duplicate status checks/retries.
  ws.onerror = () => ws.close();

  return ws;
}
