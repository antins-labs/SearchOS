// TypeScript types aligned with backend Pydantic models

export interface WorkerInfo {
  name: string;
  intent: string;
  scope: string;
  status: "pending" | "running" | "completed" | "error";
  events: WSEvent[];
}

export interface SchemaTableRequest {
  table_id: string;
  table_label?: string;
  entities?: string[];
  attrs: string[];
  primary_key?: string[];
  row_label?: string;
}

export interface SchemaRelationRequest {
  from_table: string;
  to_table: string;
  foreign_key: string[];
  target_columns?: string[];
  kind: "one_to_many" | "many_to_many";
  label?: string;
}

export interface SearchRequest {
  query: string;
  entities?: string[];
  attrs?: string[];
  table_label?: string;
  primary_key?: string[];
  row_label?: string;
  tables?: SchemaTableRequest[];
  relations?: SchemaRelationRequest[];
  max_time?: number;
  effort?: EffortLevel;
  skills?: SkillOverrides;
  trusted_domains?: string[];
  excluded_domains?: string[];
  sources?: SourceSelection;
  /** Follow-up: extend this prior session (same workspace + coverage table). */
  follow_up_to?: string;
  /** Prior turns echoed back so the orchestrator sees the conversation. */
  history?: { query: string; answer: string }[];
}

export interface LocalSourceSelection {
  library_id: string;
  selection: "library" | "documents";
  document_ids: string[];
  model_access: true;
}

export interface SourceSelection {
  mode: "web" | "local" | "hybrid";
  local?: LocalSourceSelection;
}

export interface LocalLibrary {
  library_id: string;
  name: string;
  created_at: string;
}

export interface LocalIndexJob {
  job_id: string;
  library_id: string;
  document_id: string;
  source_revision: string;
  file_name: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  created_at: string;
  updated_at: string;
  error: string;
  attempt: number;
  recap_segments_completed: number;
  recap_segments_total: number;
}

export interface NetworkImportJob {
  job_id: string;
  idempotency_key: string;
  library_id: string;
  source_url: string;
  title: string;
  index_after_save: boolean;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage: "fetch" | "save" | "saved" | "parse" | "recap_catalog" | "indexed" | "saved_unindexed" | "failed" | "cancelled";
  document_id: string;
  created_at: string;
  updated_at: string;
  error: string;
  attempt: number;
  recap_segments_completed: number;
  recap_segments_total: number;
}

export interface LocalDocument {
  document_id: string;
  name: string;
  kind: string;
  size_bytes: number;
  status: "saved" | "ready" | "partial" | "failed";
  parse_status: "pending" | "ready" | "partial" | "failed";
  recap_status: "pending" | "ready" | "partial" | "failed";
  catalog_status: "pending" | "ready" | "partial" | "failed";
  recap_segments_completed: number;
  recap_segments_total: number;
  searchable: boolean;
  source_revision: string;
  warnings: string[];
  cached?: boolean;
  index_job?: LocalIndexJob | null;
  origin?: Record<string, unknown> | null;
}

export interface LocalGraphNode {
  id: string;
  node_type: "index" | "subindex" | "document";
  label: string;
  original_name?: string;
  summary: string;
  subindex_id?: string;
  document_id?: string;
  document_kind?: string;
  character_count?: number;
  document_count?: number;
  size_bytes?: number;
  searchable?: boolean;
  parse_status?: "ready" | "partial" | "failed";
  recap_status?: "ready" | "partial" | "failed" | "pending";
  recap_error?: string;
  catalog_status?: "ready" | "partial" | "failed";
  source_revision?: string;
  warnings?: string[];
}

export interface LocalGraphEdge {
  source: string;
  target: string;
  relation: "contains" | "classifies" | "pending_catalog";
}

export interface LocalLibraryGraph {
  library_id: string;
  name: string;
  nodes: LocalGraphNode[];
  edges: LocalGraphEdge[];
}

export interface LocalDocumentOutlineEntry {
  entry_id: string;
  title: string;
  summary: string;
  location_label: string;
  character_count: number;
  segment_ids: string[];
}

export interface LocalDocumentSegmentMeta {
  segment_id: string;
  title: string;
  location_label: string;
  character_count: number;
  extraction_method: string;
}

export interface LocalDocumentIndex {
  library_id: string;
  document_id: string;
  name: string;
  summary: string;
  outline: LocalDocumentOutlineEntry[];
  segments: LocalDocumentSegmentMeta[];
}

export interface LocalDocumentSegmentChunk {
  segment_id: string;
  title: string;
  location_label: string;
  content: string;
  offset: number;
  next_offset: number | null;
  total_characters: number;
}

export interface LocalCitation {
  citation_id: string;
  ref_id: string;
  source_kind: "local";
  library_id: string;
  document_id: string;
  file_name: string;
  source_revision: string;
  location_label: string;
  locators: Record<string, unknown>[];
  representation_id: string;
  content: string;
  preview_mode: "pdf" | "image" | "text" | "office" | "unsupported";
  warnings: string[];
}

export interface RepairCellTarget {
  table_id: string;
  entity: string;
  attribute: string;
}

export interface RepairRequest {
  cells: RepairCellTarget[];
  max_time?: number;
  effort?: EffortLevel;
  skills?: SkillOverrides;
  trusted_domains?: string[];
  excluded_domains?: string[];
  history?: { query: string; answer: string }[];
}

// ---- Settings (mirrors web/api/routes/settings.py views) ----

export type EffortLevel = "low" | "medium" | "high" | "max";

export interface LocalizedCopy { zh: string; en: string }

export interface ModelPurpose {
  role: string;
  label: LocalizedCopy;
  description: LocalizedCopy;
  guidance: LocalizedCopy;
  allocation: "main" | "text" | "vision" | null;
}

export interface ModelPurposeGroup {
  id: string;
  label: LocalizedCopy;
  purposes: ModelPurpose[];
}

export interface SkillOverrides {
  access_only?: string[] | null;
  access_deny?: string[];
  strategy_deny?: string[];
  orchestrator_deny?: string[];
}

export interface SkillInfo {
  package_format?: "portable" | "legacy";
  package_hash?: string;
  name: string;
  description: string;
  status: string;
  enabled: boolean;
}

export interface SkillsView {
  enable_skills: boolean;
  enable_access_skill_generation: boolean;
  access_skill_max_per_run: number;
  access_mode: "router" | "only";
  categories: Record<string, SkillInfo[]>; // orchestrator / access / strategy
}

export interface ProviderKeyEnvInfo {
  env: string;
  key_set: boolean;
}

export interface ProviderConnectionInfo {
  protocol: "openai_compatible" | "openai" | "anthropic";
  api_base: string;
  api_key_envs: ProviderKeyEnvInfo[]; // first entry is the default key
  thinking_style: "chat_template_kwargs" | "enable_thinking" | "none";
  label: string;
  key_set: boolean; // any of the connection's keys present
}

export interface ProfileInfo {
  model: string;
  provider: string;
  api_base: string;
  api_key_env: string;
  api_key_set: boolean;
  temperature: number | null;
  max_tokens: number | null;
  rpm: number;
  tpm: number;
  enable_thinking: boolean;
  thinking_style: "chat_template_kwargs" | "enable_thinking" | "none";
  custom: boolean;
  provider_ref: string | null; // name of the provider connection this card points at
  overridden: string[]; // base-profile fields overridden via web
}

export interface SearchProviderInfo {
  name: string;
  label: string;
  api_key_env: string;
  key_set: boolean;
  doc_url: string;
}

export interface ModelsView {
  active_provider_preset: string;
  profiles: Record<string, ProfileInfo>;
  provider_connections: Record<string, ProviderConnectionInfo>;
  roles: Record<string, string>;
  purpose_groups?: ModelPurposeGroup[]; // Older running APIs do not provide this catalog.
  role_overrides: Record<string, string>;
  search: {
    resolved: string;
    configured: string | null;
    providers: SearchProviderInfo[];
  };
  browser_backend: string;
  jina_api_key_set: boolean;
}

export interface EffortView {
  level: EffortLevel;
  knobs: Record<string, number>;
  overrides: Record<string, number>;
  levels: Record<EffortLevel, Record<string, number>>;
}

export interface RunDefaultsView {
  max_time_s: number;
  search_max_results: number;
  enable_skills: boolean;
  enable_explore_batch: boolean;
  enable_web_image_read: boolean;
  web_image_read_mode: "auto" | "native" | "vision";
  jina_retain_images: "auto" | "alt" | "all";
  effective_jina_retain_images: "alt" | "all";
  web_image_capability: {
    status: "unknown" | "supported" | "unsupported";
    checked_at: number | null;
    reason: string;
  };
  web_image_agent_model: string;
  web_image_vision_model: string;
}

// First-class runtime knobs not covered by effort. Proxy / cache dir are not
// secrets, so their resolved values round-trip (unlike API keys).
export interface AdvancedView {
  llm_max_retries: number;
  orch_coverage_stall_rounds: number;
  browser_disk_cache_dir: string;
  https_proxy: string;
  search_max_results: number;
  use_layered_context: boolean;
  overridden: string[]; // which knobs the overlay currently pins
}

export interface SettingsData {
  effort: EffortView;
  skills: SkillsView;
  models: ModelsView;
  run_defaults: RunDefaultsView;
  advanced: AdvancedView;
  middleware?: MiddlewareView;
}

export interface MiddlewareComponent {
  id: string;
  category: "context" | "extraction" | "sensor";
  label: LocalizedCopy;
  description: LocalizedCopy;
  hooks: string[];
  condition: LocalizedCopy | null;
}

export interface MiddlewarePipeline {
  id: string;
  label: LocalizedCopy;
  available: string[];
  selected: string[];
  defaults: string[];
  customized: boolean;
}

export interface MiddlewareView {
  catalog: MiddlewareComponent[];
  pipelines: MiddlewarePipeline[];
}

export interface ProviderPresetInfo {
  name: string;
  label: string;
  group: string;
  api_key_env: string;
  requires_key: boolean;
  requires_model: boolean;
  main_model: string;
  fast_model: string;
  api_base: string;
  protocol: "openai_compatible" | "openai" | "anthropic";
  thinking_style: "chat_template_kwargs" | "enable_thinking" | "none";
  temperature_ok: boolean;
  doc_url: string;
  notes: string;
  key_set: boolean;
}

export interface ProvidersResponse {
  active: string;
  groups: { name: string; presets: ProviderPresetInfo[] }[];
  overrides: { model: string; fast_model: string; api_base: string };
}

export interface ProviderSwitchResult {
  models: ModelsView;
  cleared_role_overrides: string[];
  cleared_profile_overrides: string[];
  warnings: string[];
}

export interface CoverageCell {
  value: string | string[];
  status: "missing" | "filled" | "uncertain" | "hard_cell";
  source?: string | string[];
  confidence?: number;
  supporting_evidence_ids?: string[];
  primary_evidence_id?: string;
  has_conflict?: boolean;
  conflict_evidence_ids?: string[];
}

export interface TableSchema {
  table_id: string;
  table_label?: string;
  entities: string[];
  attributes: string[];
  primary_key?: string[];
  row_label?: string;
  schema_mode?: "closed" | "column_only";
  data_columns?: string[];
  attribute_types?: Record<string, "scalar" | "list">;
}

export interface ForeignKey {
  target_table: string;
  columns: string[];
  target_columns: string[];
}

export interface Relation {
  from_table: string;
  foreign_key: ForeignKey;
  kind: "one_to_many" | "many_to_one" | "many_to_many";
  label?: string;
}

export interface CoverageMap {
  tables: Record<string, TableSchema>;
  relations: Relation[];
  active_table: string;
  // Cell keys: "{table_id}/{entity}.{attribute}"
  cells: Record<string, CoverageCell>;
  evidence_bindings?: Record<string, CellEvidenceBinding[]>;
}

export interface CellEvidenceBinding {
  evidence_id: string;
  value: string;
  alignment: "full" | "partial" | "loose";
  status: "active" | "rejected" | "superseded";
}

export interface EvidenceNode {
  id: string;
  claim: string;
  value?: string;
  source: string;
  confidence: number;
  entity: string;
  attribute: string;
  quality_score?: number;
  table_id?: string;
  alignment?: "full" | "partial" | "loose";
  alignment_note?: string;
  source_excerpt?: string;
  source_authority?: "official" | "industry_pr" | "aggregator" | "news" | "blog" | "unclear" | string;
  status?: "active" | "rejected" | "superseded";
  created_at?: number;
  page_id?: string;
  local_source_metadata?: {
    library_id?: string;
    document_id?: string;
    file_name?: string;
    source_revision?: string;
    generation?: string;
    representation_id?: string;
    locators?: Record<string, unknown>[];
  };
}

export interface EvidenceEdge {
  from_id: string;
  to_id: string;
  relation: "support" | "conflict" | "refine";
}

export interface ResolveEvidenceRequest extends RepairCellTarget {
  evidence_id: string;
}

export interface ResolveEvidenceResponse {
  status: "resolved";
  selected_evidence_id: string;
  superseded_evidence_ids: string[];
  search_state: SearchState;
}

export interface TaskEvidenceBinding {
  task_id: string;
  evidence_id: string;
  relation: "supports" | "contradicts" | "context";
}

export interface FrontierTask {
  id: string;
  question: string;
  kind?: "search" | "write" | "explore";
  status: "pending" | "running" | "completed" | "blocked" | "cancelled" | "open" | "exploring" | "resolved";
  priority: number;
  result_mode?: "findings" | "table";
  blocked_by?: string[];
  target_cells?: string[];
  table_id?: string;
  agent_type?: string;
  skills?: string[];
  max_searches?: number | null;
  task_prompt?: string;
  assigned_agent_id?: string;
  assigned_worker?: string;
  attempts?: number;
  created_by?: string;
  planner?: "orchestrator" | "llm" | "deterministic" | "";
  resolution: string;
}

export interface BudgetState {
  max_queries: number;
  consumed_queries: number;
  max_time_s: number;
  elapsed_s: number;
  max_iterations: number;
  current_iteration: number;
}

export interface DAGNode {
  id: string;
  question: string;
  agent_type: string;
  skills: string[];
  depends_on: string[];
  produces: string[];
  status: "pending" | "ready" | "running" | "completed" | "failed" | "skipped";
  result_summary: string;
  error: string;
  started_at: string;
  completed_at: string;
}

export interface TaskDAG {
  nodes: Record<string, DAGNode>;
}

export interface SearchState {
  intent: string;
  task_type: "wide" | "deep" | "local" | "hybrid";
  frontier: { questions: FrontierTask[] };
  explored_paths: { query: string; useful: boolean }[];
  evidence_graph: { nodes: EvidenceNode[]; edges: EvidenceEdge[]; task_bindings?: TaskEvidenceBinding[] };
  research_mode?: "table" | "findings";
  source_scope?: { mode: "web" | "local" | "hybrid"; library_id?: string; selection?: "library" | "documents"; document_ids?: string[]; documents: { document_id: string; relative_path?: string }[]; unavailable_sources?: Record<string, string> } | null;
  coverage_map: CoverageMap;
  strategy_log: { patterns: { pattern: string; effective: boolean; context: string }[] };
  budget: BudgetState;
  task_dag: TaskDAG;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_prompt_tokens?: number;
  llm_calls: number;
  cache_hit_calls?: number;
  cache_hit_rate?: number;
  by_role?: Record<string, {
    prompt_tokens: number;
    completion_tokens: number;
    cached_prompt_tokens?: number;
    llm_calls: number;
    cache_hit_calls?: number;
  }>;
}

export interface TokenPhaseUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_prompt_tokens?: number;
  llm_calls: number;
  cache_hit_calls?: number;
}

export interface ModelDistributionItem {
  profile: string;
  model: string;
  provider: string;
}

export interface SearchResult {
  revision?: string;
  not_modified?: boolean;
  status: "running" | "completed" | "error";
  session_id: string;
  /** Full final answer (event-stream previews are truncated server-side). */
  answer?: string;
  query?: string;
  coverage_score?: number | null;
  evidence_count?: number;
  total_queries?: number;
  total_steps?: number;
  elapsed_s?: number;
  eval_verdict?: string;
  workspace_path?: string;
  token_usage?: TokenUsage;
  token_phases?: Record<string, TokenPhaseUsage>;
  tool_counts?: Record<string, number>;
  model_distribution?: Record<string, ModelDistributionItem>;
  search_state?: SearchState;
  error?: string;
}

export interface DiagnosticBase {
  ok: boolean;
  kind: "provider" | "search" | "browser";
  latency_ms: number;
  error?: string | null;
}

export interface ProviderDiagnostic extends DiagnosticBase {
  kind: "provider";
  role: string;
  provider?: string;
  model?: string;
  thinking_enabled?: boolean;
  thinking_style?: string;
  thinking_status?: "not_requested" | "not_configured" | "accepted" | "observed";
  response_preview?: string;
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
}

export interface SearchDiagnostic extends DiagnosticBase {
  kind: "search";
  provider: string;
  result_count?: number;
  results?: { title: string; domain: string }[];
}

export interface BrowserDiagnostic extends DiagnosticBase {
  kind: "browser";
  backend: string;
  implementation?: string;
  status_code?: number;
  title?: string;
  content_chars?: number;
  proxy: { configured: boolean; endpoint: string };
}

export interface FileNode {
  name: string;
  type: "file" | "directory";
  path: string;
  size?: number;
  children?: FileNode[];
}

// WebSocket event — loose type to avoid TS union narrowing issues
export interface WSEvent {
  type: string;
  [key: string]: unknown;
}

export type SteeringMode = "immediate" | "after_tool";

export interface LiveFollowUp {
  id: string;
  text: string;
  mode: SteeringMode;
  status: "queued" | "delivered" | "cancelled";
}

export interface SteeringSnapshot {
  revision: number;
  messages: LiveFollowUp[];
}

export interface SteeringSubmission {
  status: "queued";
  // Older running API processes acknowledge submission without queue metadata.
  message_id?: string;
  mode?: SteeringMode;
  queue?: SteeringSnapshot;
}
