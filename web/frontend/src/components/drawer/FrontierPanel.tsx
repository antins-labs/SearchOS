"use client";

import { useState } from "react";
import {
  Ban,
  CheckCircle2,
  ChevronDown,
  Circle,
  CirclePause,
  Loader2,
  Sparkles,
} from "lucide-react";

import type { FrontierTask } from "@/lib/types";

type Filter = "all" | "active" | "done";

const STATUS = {
  pending: { label: "Pending", icon: Circle, className: "text-ink-faint" },
  open: { label: "Pending", icon: Circle, className: "text-ink-faint" },
  running: { label: "Running", icon: Loader2, className: "text-accent-ink" },
  exploring: { label: "Running", icon: Loader2, className: "text-accent-ink" },
  completed: { label: "Completed", icon: CheckCircle2, className: "text-ok" },
  resolved: { label: "Completed", icon: CheckCircle2, className: "text-ok" },
  blocked: { label: "Blocked", icon: CirclePause, className: "text-warn" },
  cancelled: { label: "Cancelled", icon: Ban, className: "text-err" },
} as const;

const isActive = (task: FrontierTask) => ["pending", "open", "running", "exploring", "blocked"].includes(task.status);
const isDone = (task: FrontierTask) => ["completed", "resolved", "cancelled"].includes(task.status);

function TaskRow({ task }: { task: FrontierTask }) {
  const [expanded, setExpanded] = useState(false);
  const status = STATUS[task.status] ?? STATUS.pending;
  const Icon = status.icon;
  const agent = task.assigned_agent_id || task.assigned_worker || task.agent_type;
  const details = task.task_prompt || task.resolution;

  return (
    <div className="border-b border-line last:border-b-0">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2"
      >
        <Icon className={`mt-0.5 shrink-0 ${status.className} ${task.status === "running" || task.status === "exploring" ? "animate-spin" : ""}`} size={15} />
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 text-[12.5px] font-medium leading-5 text-ink">{task.question}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-ink-faint">
            <span className={status.className}>{status.label}</span>
            {task.kind && <span>{task.kind}</span>}
            {agent && <span className="truncate">{agent.replaceAll("_", " ")}</span>}
            {task.planner && (
              <span className="inline-flex items-center gap-1 text-accent-ink">
                {(task.planner === "llm" || task.planner === "orchestrator") && <Sparkles size={10} />}
                {task.planner === "orchestrator"
                  ? "Orchestrator"
                  : task.planner === "llm" ? "LLM planned" : "Safe fallback"}
              </span>
            )}
          </div>
        </div>
        <ChevronDown className={`mt-0.5 shrink-0 text-ink-faint transition-transform ${expanded ? "rotate-180" : ""}`} size={14} />
      </button>

      {expanded && (
        <div className="px-4 pb-3 pl-12">
          {(task.target_cells ?? []).length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {(task.target_cells ?? []).map((cell, index) => (
                <span key={`${cell}:${index}`} className="max-w-full truncate rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-dim" title={cell}>
                  {task.table_id ? `${task.table_id}/${cell}` : cell}
                </span>
              ))}
            </div>
          )}
          {details && (
            <p className="whitespace-pre-wrap text-[11px] leading-5 text-ink-dim">{details}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-ink-faint">
            <span>ID {task.id}</span>
            <span>Priority {Number(task.priority ?? 0).toFixed(2)}</span>
            {typeof task.attempts === "number" && <span>{task.attempts} attempts</span>}
            {typeof task.max_searches === "number" && <span>{task.max_searches} search cap</span>}
            {task.created_by && <span>Created by {task.created_by}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export default function FrontierPanel({ tasks }: { tasks: FrontierTask[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const active = tasks.filter(isActive).length;
  const done = tasks.filter(isDone).length;
  const visible = tasks.filter((task) => (
    filter === "all" || (filter === "active" ? isActive(task) : isDone(task))
  ));

  return (
    <div className="min-w-0">
      <div className="sticky top-[39px] z-[9] flex items-center gap-1 border-b border-line bg-surface px-3 py-2">
        {([
          ["all", `All ${tasks.length}`],
          ["active", `Active ${active}`],
          ["done", `Done ${done}`],
        ] as [Filter, string][]).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
            className={`rounded-lg px-2.5 py-1.5 text-[11.5px] transition-colors ${filter === value ? "bg-accent-soft font-medium text-accent-ink" : "text-ink-dim hover:bg-surface-2 hover:text-ink"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {visible.length > 0 ? (
        <div>{visible.map((task) => <TaskRow key={task.id} task={task} />)}</div>
      ) : (
        <div className="px-4 py-6 text-center text-[12px] text-ink-faint">
          {tasks.length ? "No tasks in this view" : "Frontier tasks appear here as research is planned"}
        </div>
      )}
    </div>
  );
}
