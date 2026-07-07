// TypeScript types aligned with backend Pydantic models

export interface SearchRequest {
  query: string;
  type?: "wide" | "deep" | "local" | "hybrid";
  entities?: string[];
  attrs?: string[];
  max_queries?: number;
  max_time?: number;
  checkpoint?: number;
  enable_teams?: boolean;
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
