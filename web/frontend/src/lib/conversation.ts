import type { SearchState, WSEvent } from "./types";
import type { WorkerInfo } from "@/hooks/useSearch";

export interface Turn {
  id: string;
  query: string;
  sessionId: string | null;
  status: "running" | "completed" | "error";
  events: WSEvent[];
  workers: WorkerInfo[];
  searchState: SearchState | null;
  answer: string;
  meta: {
    coverageScore?: number;
    evidenceCount?: number;
    elapsed?: number;
    verdict?: string | null;
  };
  error?: string | null;
}
