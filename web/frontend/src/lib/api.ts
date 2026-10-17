// REST + WebSocket API client

import type {
  AdvancedView,
  SteeringMode,
  SteeringSnapshot,
  SteeringSubmission,
  BrowserDiagnostic,
  EffortLevel,
  EffortView,
  FileNode,
  ModelsView,
  MiddlewareView,
  LocalCitation,
  LocalDocument,
  LocalDocumentIndex,
  LocalDocumentSegmentChunk,
  LocalIndexJob,
  LocalLibrary,
  LocalLibraryGraph,
  NetworkImportJob,
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

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || (typeof window === "undefined" ? "http://localhost:8000" : "");
const REQUEST_TIMEOUT_MS = 12000;

export async function request<T>(
  path: string,
  init: RequestInit = {},
  options: {
    timeoutMs?: number;
    errorPrefix?: string;
    noContent?: boolean;
    repair?: boolean;
  } = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), options.timeoutMs ?? REQUEST_TIMEOUT_MS);
  const signal = init.signal
    ? AbortSignal.any([init.signal, controller.signal])
    : controller.signal;
  try {
    const headers = new Headers(init.headers);
    if (init.method && !["GET", "HEAD"].includes(init.method)) headers.set("X-SearchOS-Request", "1");
    const response = await fetch(`${API_BASE}${path}`, { ...init, credentials: "include", headers, signal });
    if (!response.ok) {
      if (response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("searchos:unauthorized"));
      let detail = response.statusText;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
        else if (Array.isArray(body.detail)) detail = body.detail.map((item: unknown) => typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)).join("; ");
        else if (typeof body.detail?.detail === "string") detail = body.detail.detail;
      } catch { /* 非 JSON 错误保留 HTTP 状态说明。 */ }
      if (options.repair && response.status === 404 && detail === "Not Found") {
        throw new Error("Repair API unavailable — restart the SearchOS API to load the current WebUI routes");
      }
      throw new Error(options.errorPrefix ? `${options.errorPrefix}: ${detail}` : detail);
    }
    return options.noContent ? undefined as T : await response.json() as T;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Request timed out");
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

// ---- REST ----

export async function getHealth(): Promise<{ status: string; version?: string } | null> {
  try {
    return await request("/api/health", { cache: "no-store" });
  } catch {
    return null;
  }
}

export async function startSearch(req: SearchRequest): Promise<{ session_id: string }> {
  return request("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  }, { errorPrefix: "Search failed" });
}

export async function startRepair(
  sessionId: string,
  req: RepairRequest,
): Promise<RepairStartResponse> {
  return request(
    `/api/search/${sessionId}/repair`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
    { timeoutMs: 35000, errorPrefix: "Repair failed", repair: true },
  );
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
  return request(`/api/search/${sessionId}/evidence/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  }, { errorPrefix: "Resolve evidence failed" });
}

export async function stopSearch(sessionId: string): Promise<void> {
  return request(`/api/search/${sessionId}/stop`, { method: "POST" }, { noContent: true, errorPrefix: "Stop failed" });
}

export async function steerSearch(sessionId: string, message: string, mode: SteeringMode = "immediate"): Promise<SteeringSubmission> {
  return request(`/api/search/${sessionId}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode }),
  }, { errorPrefix: "追问发送失败" });
}

export function isSteeringSnapshot(value: unknown): value is SteeringSnapshot {
  if (!value || typeof value !== "object") return false;
  const snapshot = value as Partial<SteeringSnapshot>;
  return Number.isSafeInteger(snapshot.revision) && (snapshot.revision ?? -1) >= 0
    && Array.isArray(snapshot.messages) && snapshot.messages.every((message) => (
      message && typeof message.id === "string" && typeof message.text === "string"
      && ["immediate", "after_tool"].includes(message.mode)
      && ["queued", "delivered", "cancelled"].includes(message.status)
    ));
}

function requireSteeringSnapshot(value: unknown): SteeringSnapshot {
  if (!isSteeringSnapshot(value)) {
    throw new Error("追问队列响应不兼容，请重启 SearchOS API 后重试");
  }
  return value;
}

export async function getSteeringQueue(sessionId: string): Promise<SteeringSnapshot> {
  return requireSteeringSnapshot(await request(`/api/search/${sessionId}/steer`, { cache: "no-store" }, {
    errorPrefix: "无法读取追问队列（旧版后端需重启 SearchOS API）",
  }));
}

export async function promoteSteeringMessage(sessionId: string, messageId: string): Promise<SteeringSnapshot> {
  return requireSteeringSnapshot(await request(`/api/search/${sessionId}/steer/${encodeURIComponent(messageId)}/promote`, {
    method: "POST",
  }));
}

export async function removeSteeringMessage(sessionId: string, messageId: string): Promise<SteeringSnapshot> {
  return requireSteeringSnapshot(await request(`/api/search/${sessionId}/steer/${encodeURIComponent(messageId)}`, {
    method: "DELETE",
  }));
}

export async function getSearchResult(sessionId: string): Promise<SearchResult> {
  return request(`/api/search/${sessionId}`, {}, { errorPrefix: "Get result failed" });
}

export async function getSearchState(sessionId: string, revision = ""): Promise<SearchResult> {
  return request(`/api/search/${sessionId}/state${revision ? `?revision=${encodeURIComponent(revision)}` : ""}`, {}, { errorPrefix: "Get state failed" });
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
  return request(`/api/history${suffix}`, { cache: "no-store" }, { errorPrefix: "Load history failed" });
}

export async function loadHistory(sessionId: string): Promise<HistoryDetail> {
  return request(`/api/history/${sessionId}`, {}, { errorPrefix: "Load session failed" });
}

export interface HistoryBranchResponse {
  session_id: string;
  source_session_id: string;
  source_turn_index: number;
  status: "ready";
}

export async function branchHistoryTurn(sessionId: string, turnIndex: number): Promise<HistoryBranchResponse> {
  return request(`/api/history/${sessionId}/turns/${turnIndex}/branch`, {
    method: "POST",
  }, { errorPrefix: "Create branch failed" });
}

export async function updateHistoryAssets(
  sessionId: string,
  patch: HistoryAssetPatch,
): Promise<HistoryAssetPatch & { session_id: string; title: string }> {
  return request(`/api/history/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  }, { errorPrefix: "Update failed" });
}

export async function deleteHistory(sessionId: string): Promise<void> {
  return request(`/api/history/${sessionId}`, { method: "DELETE" }, { noContent: true, errorPrefix: "Delete failed" });
}

export async function getWorkspaceFiles(sessionId: string): Promise<{ tree: FileNode[] }> {
  return request(`/api/workspace/${sessionId}/files`, {}, { errorPrefix: "Get files failed" });
}

export async function getFileContent(sessionId: string, path: string): Promise<{ content: string }> {
  return request(`/api/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`, {}, { errorPrefix: "Get file failed" });
}

// ---- Local libraries ----

export async function listLocalLibraries(): Promise<LocalLibrary[]> {
  return request("/api/local/libraries", { cache: "no-store" }, { errorPrefix: "Load local libraries failed" });
}

export async function createLocalLibrary(name = "本地资料"): Promise<LocalLibrary> {
  return request("/api/local/libraries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }, { errorPrefix: "Create local library failed" });
}

export async function renameLocalLibrary(libraryId: string, name: string): Promise<LocalLibrary> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }, { errorPrefix: "Rename local library failed" });
}

export async function listLocalDocuments(libraryId: string): Promise<LocalDocument[]> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/documents`, {
    cache: "no-store",
  }, { errorPrefix: "Load local documents failed" });
}

export async function deleteLocalLibrary(libraryId: string): Promise<{ deleted: string }> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}`, { method: "DELETE" },
    { errorPrefix: "删除资料库失败", timeoutMs: 60000 });
}

export async function editLocalDocument(libraryId: string, documentId: string, name: string): Promise<LocalLibraryGraph> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  }, { errorPrefix: "编辑文档失败" });
}

export async function deleteLocalDocument(libraryId: string, documentId: string): Promise<LocalLibraryGraph> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  }, { errorPrefix: "删除文档失败", timeoutMs: 60000 });
}

export async function saveLocalTopic(libraryId: string, title: string, summary: string, topicId?: string): Promise<LocalLibraryGraph> {
  const base = `/api/local/libraries/${encodeURIComponent(libraryId)}/topics`;
  return request(topicId ? `${base}/${encodeURIComponent(topicId)}` : base, {
    method: topicId ? "PATCH" : "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, summary }),
  }, { errorPrefix: "保存主题失败" });
}

export async function deleteLocalTopic(libraryId: string, topicId: string): Promise<LocalLibraryGraph> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/topics/${encodeURIComponent(topicId)}`, {
    method: "DELETE",
  }, { errorPrefix: "删除主题失败" });
}

export async function importNetworkSource(
  libraryId: string,
  sourceUrl: string,
  options: { title?: string; indexAfterSave?: boolean; sessionId?: string; pageId?: string } = {},
): Promise<NetworkImportJob> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/imports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_url: sourceUrl,
      title: options.title ?? "",
      index_after_save: options.indexAfterSave ?? true,
      session_id: options.sessionId ?? "",
      page_id: options.pageId ?? "",
    }),
  }, { errorPrefix: "Save source failed" });
}

export async function listNetworkImports(libraryId: string): Promise<NetworkImportJob[]> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/imports`, {
    cache: "no-store",
  }, { errorPrefix: "Load source imports failed" });
}

export async function getLocalLibraryGraph(libraryId: string): Promise<LocalLibraryGraph> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/graph`, {
    cache: "no-store",
  }, { errorPrefix: "Load local library graph failed" });
}

export async function setLocalDocumentTopics(
  libraryId: string,
  documentId: string,
  subindexIds: string[],
): Promise<LocalLibraryGraph> {
  return request(
    `/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}/topics`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subindex_ids: subindexIds }),
    },
    { errorPrefix: "Update local document topics failed" },
  );
}

export async function retryLocalTopicRecaps(libraryId: string): Promise<LocalLibraryGraph> {
  return request(`/api/local/libraries/${encodeURIComponent(libraryId)}/topic-recaps/retry`, {
    method: "POST",
  }, { errorPrefix: "更新主题摘要失败" });
}

export async function getLocalDocumentIndex(
  libraryId: string,
  documentId: string,
): Promise<LocalDocumentIndex> {
  return request(
    `/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}/index`,
    { cache: "no-store" },
    { errorPrefix: "Load local document index failed" },
  );
}

export async function getLocalDocumentSegment(
  libraryId: string,
  documentId: string,
  segmentId: string,
  offset = 0,
): Promise<LocalDocumentSegmentChunk> {
  const params = new URLSearchParams({ segment_id: segmentId, offset: String(offset) });
  return request(
    `/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}/segment?${params.toString()}`,
    { cache: "no-store" },
    { errorPrefix: "Load local document segment failed" },
  );
}

export function localDocumentOriginalUrl(libraryId: string, documentId: string): string {
  return `${API_BASE}/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}/original`;
}

export function localDocumentPreviewUrl(
  libraryId: string,
  documentId: string,
  documentKind: string,
): string {
  const original = localDocumentOriginalUrl(libraryId, documentId);
  if (!["docx", "pptx", "xlsx"].includes(documentKind.toLowerCase())) return original;
  return `${API_BASE}/api/local/libraries/${encodeURIComponent(libraryId)}/documents/${encodeURIComponent(documentId)}/preview`;
}

export async function cancelLocalIndexJob(libraryId: string, jobId: string): Promise<LocalIndexJob> {
  return request(
    `/api/local/libraries/${encodeURIComponent(libraryId)}/index-jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
    { errorPrefix: "Cancel local index job failed" },
  );
}

export async function retryLocalIndexJob(libraryId: string, jobId: string): Promise<LocalIndexJob> {
  return request(
    `/api/local/libraries/${encodeURIComponent(libraryId)}/index-jobs/${encodeURIComponent(jobId)}/retry`,
    { method: "POST" },
    { errorPrefix: "Retry local index job failed" },
  );
}

export interface LocalUploadProgress {
  loaded: number;
  total: number;
  percent: number;
  phase: "uploading" | "parsing";
}

export async function uploadLocalDocument(
  libraryId: string,
  file: File,
  onProgress?: (progress: LocalUploadProgress) => void,
): Promise<LocalDocument> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file, file.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/local/libraries/${encodeURIComponent(libraryId)}/uploads`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-SearchOS-Request", "1");
    xhr.timeout = 180000;
    xhr.upload.onprogress = (event) => {
      const total = event.lengthComputable ? event.total : file.size;
      const percent = total > 0 ? Math.min(100, Math.round((event.loaded / total) * 100)) : 0;
      onProgress?.({
        loaded: event.loaded,
        total,
        percent,
        phase: percent >= 100 ? "parsing" : "uploading",
      });
    };
    xhr.upload.onload = () => {
      onProgress?.({ loaded: file.size, total: file.size, percent: 100, phase: "parsing" });
    };
    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch { /* 非 JSON 错误使用 HTTP 状态。 */ }
      if (xhr.status >= 200 && xhr.status < 300 && payload) {
        resolve(payload as LocalDocument);
        return;
      }
      const detail = payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail?: unknown }).detail)
        : xhr.statusText || `HTTP ${xhr.status}`;
      reject(new Error(`Upload ${file.name} failed: ${detail}`));
    };
    xhr.onerror = () => reject(new Error(`Upload ${file.name} failed: backend unreachable`));
    xhr.ontimeout = () => reject(new Error(`Upload ${file.name} failed: request timed out`));
    xhr.send(body);
  });
}

export async function resolveLocalCitation(refId: string): Promise<LocalCitation> {
  return request("/api/local/citations/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref_id: refId }),
  }, { errorPrefix: "Open local source failed" });
}

export function localOriginalUrl(citation: LocalCitation): string {
  const base = `${API_BASE}/api/local/libraries/${encodeURIComponent(citation.library_id)}/documents/${encodeURIComponent(citation.document_id)}/original`;
  const pageLocator = citation.locators.find((locator) => (
    typeof locator.page_start === "number" && locator.page_start > 0
  ));
  return pageLocator ? `${base}#page=${pageLocator.page_start}` : base;
}

export function localPreviewUrl(citation: LocalCitation): string {
  if (citation.preview_mode !== "office") return localOriginalUrl(citation);
  const base = `${API_BASE}/api/local/libraries/${encodeURIComponent(citation.library_id)}/documents/${encodeURIComponent(citation.document_id)}/preview`;
  const slideLocator = citation.locators.find((locator) => (
    typeof locator.slide_number === "number" && locator.slide_number > 0
  ));
  return slideLocator ? `${base}#page=${slideLocator.slide_number}` : base;
}

// ---- Settings ----

export async function getSettings(): Promise<SettingsData | null> {
  try {
    return await request("/api/settings", { cache: "no-store" });
  } catch {
    return null;
  }
}

async function putJson<T>(path: string, body: unknown, method = "PUT"): Promise<T> {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  enable_web_image_read?: boolean;
  web_image_read_mode?: "auto" | "native" | "vision";
  jina_retain_images?: "auto" | "alt" | "all";
}) => putJson<RunDefaultsView & { browser_backend: string }>("/api/settings/misc", patch);

export const detectWebImageCapability = () =>
  putJson<RunDefaultsView>("/api/settings/web-image-capability/detect", {}, "POST");

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

export const putMiddleware = (pipeline: string, selected: string[] | null) =>
  putJson<MiddlewareView>(`/api/settings/middleware/${encodeURIComponent(pipeline)}`, { selected });

// Throws on failure (unlike getSettings): the provider switcher shows an
// inline retry row and needs to distinguish errors from empty data.
export async function getProviderPresets(): Promise<ProvidersResponse> {
  return request("/api/settings/providers", { cache: "no-store" }, { errorPrefix: "Couldn't load presets" });
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
  return request(`/api/diagnostics/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, { timeoutMs: 65000, errorPrefix: "Diagnostic failed" });
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
  const wsBase = (API_BASE || window.location.origin).replace(/^http/, "ws");
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

// ---- Skill creation ----
export type SkillCreationInput = {
  kind: "site" | "task" | "trace";
  site?: string;
  text: string;
  categories: string[];
  max_requests: number;
};
export type SkillCreationJob = {
  id: string;
  input: SkillCreationInput;
  status: "queued" | "running" | "completed" | "partial" | "failed" | "interrupted";
  stage: string;
  current_index: number | null;
  requests: { name: string; category: string; description: string; subtask?: string; action?: "create" | "update"; has_draft?: boolean }[];
  results: { name: string; category: string; status: string; error?: string; path?: string; trial_path?: string; action?: "create" | "update" }[];
  error: string;
  created_at: string;
  resume_of?: { job_id: string; index: number };
};
export const createSkills = (input: SkillCreationInput) =>
  putJson<SkillCreationJob>("/api/skills/creations", input, "POST");
export const listSkillCreations = () =>
  request<SkillCreationJob[]>("/api/skills/creations", { cache: "no-store" });
export const getSkillCreation = (id: string) =>
  request<SkillCreationJob>(`/api/skills/creations/${encodeURIComponent(id)}`, { cache: "no-store" });
export const deleteSkillCreations = (ids: string[]) =>
  putJson<{ deleted: string[] }>("/api/skills/creations/delete", { ids }, "POST");
export const cancelSkillCreation = (id: string) =>
  putJson<SkillCreationJob>(`/api/skills/creations/${encodeURIComponent(id)}/cancel`, {}, "POST");

const draftUrl = (id: string, index: number) => `/api/skills/creations/${encodeURIComponent(id)}/requests/${index}/draft`;
export type SkillDraft = { name: string; revision: string; files: string[]; examples: unknown[]; validation: Record<string, unknown>; diagnostics: Record<string, unknown>; events: Record<string, unknown>[] };
export const getSkillDraft = (id: string, index: number) => request<SkillDraft>(draftUrl(id, index), { cache: "no-store" });
export const getSkillDraftFile = (id: string, index: number, path: string) =>
  request<{ path: string; content: string; revision: string }>(`${draftUrl(id, index)}/file?path=${encodeURIComponent(path)}`, { cache: "no-store" });
export const saveSkillDraftFile = (id: string, index: number, edit: { path: string; content: string; revision: string }) =>
  putJson<SkillDraft>(`${draftUrl(id, index)}/file`, edit);
export const resumeSkillCreation = (id: string, index: number) =>
  putJson<SkillCreationJob>(`/api/skills/creations/${encodeURIComponent(id)}/requests/${index}/resume`, {}, "POST");

export type SkillLibraryItem = {
  name: string; category: string; description: string; availability: string;
  enabled: boolean; package_format: string; entry: string;
};
export type SkillLibraryDetail = SkillLibraryItem & { body: string; source: string; files: string[] };
export const getSkillLibraryDetail = (category: string, name: string) => request<SkillLibraryDetail>(`/api/skills/library/${encodeURIComponent(category)}/${encodeURIComponent(name)}`);
export const getSkillLibraryFile = (category: string, name: string, path: string) => request<{ path: string; content: string }>(`/api/skills/library/${encodeURIComponent(category)}/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`);

export type SkillLibraryQuery = { q: string; category: string; page: number; page_size: number };
export type SkillLibraryResults = { items: SkillLibraryItem[]; total: number; page: number; page_size: number; pages: number; counts: Record<string, number> };
export const querySkillLibrary = (query: SkillLibraryQuery) => request<SkillLibraryResults>(`/api/skills/library/query?${new URLSearchParams({ q: query.q, category: query.category, page: String(query.page), page_size: String(query.page_size) })}`, { cache: "no-store" });
