"use client";

import { Users } from "lucide-react";
import AgentCard, { type AgentCardData } from "./AgentCard";
import { agentNum } from "./trace";

function rank(name: string): number {
  if (name.startsWith("explore") || name.startsWith("warmup")) return -1; // explore first
  if (name.startsWith("writer")) return 9999; // writer last
  return Number(agentNum(name)) || 0;
}

export default function AgentWall({
  workers,
  onSelect,
}: {
  workers: AgentCardData[];
  onSelect: (name: string) => void;
}) {
  const sorted = [...workers].sort((a, b) => rank(a.name) - rank(b.name));
  if (workers.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-ink-faint">
        <Users size={18} className="opacity-50" />
        <span className="text-xs">Agents appear here as the orchestrator dispatches them.</span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-2.5 p-3">
      {sorted.map((w) => (
        <AgentCard key={w.name} data={w} onClick={() => onSelect(w.name)} />
      ))}
    </div>
  );
}
