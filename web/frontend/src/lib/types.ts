// TypeScript types aligned with backend Pydantic models

export interface SearchRequest {
  query: string;
  type?: "wide" | "deep" | "local" | "hybrid";
  entities?: string[];
  attrs?: string[];
  max_time?: number;
  effort?: EffortLevel;
  skills?: SkillOverrides;
}

// ---- Settings (mirrors web/api/routes/settings.py views) ----

export type EffortLevel = "low" | "medium" | "high" | "max";

export interface SkillOverrides {
  access_only?: string[] | null;
  access_deny?: string[];
  strategy_deny?: string[];
  orchestrator_deny?: string[];
}

export interface SkillInfo {
  name: string;
  description: string;
  status: string;
  enabled: boolean;
}

export interface SkillsView {
  enable_skills: boolean;
  access_mode: "router" | "only";
  categories: Record<string, SkillInfo[]>; // orchestrator / access / strategy
}

export interface ProfileInfo {
  model: string;
  provider: string;
  api_base: string;
  api_key_env: string;
  api_key_set: boolean;
  temperature: number | null;
  max_tokens: number | null;
  enable_thinking: boolean;
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
  roles: Record<string, string>;
  role_overrides: Record<string, string>;
  search: {
    resolved: string;
    configured: string | null;
    providers: SearchProviderInfo[];
  };
  browser_backend: string;
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
}

export interface SettingsData {
  effort: EffortView;
  skills: SkillsView;
  models: ModelsView;
  run_defaults: RunDefaultsView;
}

export interface CoverageCell {
  value: string | string[];
  status: "missing" | "filled" | "uncertain" | "hard_cell";
  source: string | string[];
  confidence: number;
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
}

export interface EvidenceNode {
  id: string;
  claim: string;
  source: string;
  confidence: number;
  entity: string;
  attribute: string;
  quality_score: number;
  table_id?: string;
  alignment?: "full" | "partial" | "loose";
  alignment_note?: string;
  source_excerpt?: string;
}

export interface EvidenceEdge {
  from_id: string;
  to_id: string;
  relation: "support" | "conflict" | "refine";
}

export interface SubQuestion {
  id: string;
  question: string;
  status: "open" | "exploring" | "resolved";
  priority: number;
  assigned_worker: string;
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
  frontier: { questions: SubQuestion[] };
  explored_paths: { query: string; useful: boolean }[];
  evidence_graph: { nodes: EvidenceNode[]; edges: EvidenceEdge[] };
  coverage_map: CoverageMap;
  strategy_log: { patterns: { pattern: string; effective: boolean; context: string }[] };
  budget: BudgetState;
  task_dag: TaskDAG;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  llm_calls: number;
}

export interface SearchResult {
  status: "running" | "completed" | "error";
  session_id: string;
  query?: string;
  coverage_score?: number;
  evidence_count?: number;
  total_queries?: number;
  total_steps?: number;
  elapsed_s?: number;
  eval_verdict?: string;
  workspace_path?: string;
  token_usage?: TokenUsage;
  search_state?: SearchState;
  error?: string;
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
