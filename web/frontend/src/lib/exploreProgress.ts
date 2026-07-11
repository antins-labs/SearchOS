import type { WSEvent } from "./types";

export interface ExploreProgress {
  present: boolean;
  mode: "batch" | "legacy";
  phase: "planning" | "running" | "analyzing" | "completed" | "error";
  minWaves: number;
  maxWaves: number;
  wavesCompleted: number;
  currentQueries: number;
  queriesCompleted: number;
  pagesOpened: number;
  legacySteps: number;
  currentTool: string;
}

function dataOf(event: WSEvent): Record<string, unknown> | null {
  if (event.type !== "trajectory" || !event.data || typeof event.data !== "object") return null;
  return event.data as Record<string, unknown>;
}

function exploreAgent(data: Record<string, unknown>): boolean {
  return String(data.agent || "").startsWith("explore");
}

function actionOf(data: Record<string, unknown>): { name: string; args: Record<string, unknown> } {
  const raw = data.action;
  if (!raw || typeof raw !== "object") return { name: "", args: {} };
  const action = raw as Record<string, unknown>;
  const args = action.args && typeof action.args === "object"
    ? action.args as Record<string, unknown>
    : {};
  return { name: String(action.name || ""), args };
}

function queryCount(args: unknown): number {
  if (!args || typeof args !== "object") return 0;
  const queries = (args as Record<string, unknown>).queries;
  return Array.isArray(queries) ? queries.length : 0;
}

export function deriveExploreProgress(events: WSEvent[]): ExploreProgress {
  let present = false;
  let mode: ExploreProgress["mode"] = "legacy";
  let minWaves = 2;
  let maxWaves = 3;
  let startedWaves = 0;
  let wavesCompleted = 0;
  let currentQueries = 0;
  let queriesCompleted = 0;
  let pagesOpened = 0;
  let legacySteps = 0;
  let currentTool = "";
  let completed = false;
  let error = false;

  for (const event of events) {
    const data = dataOf(event);
    if (!data) continue;
    const type = String(data.type || "");

    if (type === "run_config" && data.explore && typeof data.explore === "object") {
      const config = data.explore as Record<string, unknown>;
      mode = config.batch_enabled === true ? "batch" : "legacy";
      if (typeof config.min_waves === "number") minWaves = config.min_waves;
      if (typeof config.max_waves === "number") maxWaves = config.max_waves;
    }

    if (type === "dispatch" && exploreAgent(data)) present = true;
    if (!exploreAgent(data)) continue;

    if (type === "tool_call_started") {
      present = true;
      currentTool = String(data.tool || "");
      if (currentTool === "explore_web") {
        mode = "batch";
        startedWaves += 1;
        currentQueries = queryCount(data.args);
      }
    } else if (type === "step") {
      present = true;
      const action = actionOf(data);
      currentTool = "";
      if (action.name === "explore_web") {
        mode = "batch";
        wavesCompleted += 1;
        queriesCompleted += queryCount(action.args);
        const observation = String(data.observation || data.observation_summary || "");
        const totals = observation.match(/Wave totals:\s*(\d+) queries,\s*\d+ hits,\s*(\d+) unique pages opened/i);
        if (totals) pagesOpened += Number(totals[2]);
      } else if (["search", "open", "find"].includes(action.name)) {
        legacySteps += 1;
      }
    } else if (type === "agent_error" || data.status === "error") {
      error = true;
    } else if (type === "agent_complete" || type === "agent_final") {
      completed = true;
      currentTool = "";
    }
  }

  const inFlight = mode === "batch"
    ? startedWaves > wavesCompleted && !completed
    : !!currentTool && !completed;
  const phase: ExploreProgress["phase"] = error
    ? "error"
    : completed
      ? "completed"
      : inFlight
        ? "running"
        : (wavesCompleted > 0 || legacySteps > 0)
          ? "analyzing"
          : "planning";

  return {
    present,
    mode,
    phase,
    minWaves,
    maxWaves,
    wavesCompleted,
    currentQueries,
    queriesCompleted,
    pagesOpened,
    legacySteps,
    currentTool,
  };
}
