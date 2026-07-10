"use client";

import { useState } from "react";
import { ChevronRight, RotateCcw } from "lucide-react";

import { putAdvanced, putEffort, putMisc } from "@/lib/api";
import type { EffortLevel } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import NumberField from "@/components/settings/controls/NumberField";

const LEVEL_HINTS: Record<EffortLevel, string> = {
  low: "Quick pass, small budgets",
  medium: "Balanced (default)",
  high: "Thorough, more agents & searches",
  max: "Deep dig, no expense spared",
};

const KNOB_LABELS: Record<string, string> = {
  orch_max_iterations: "Orchestrator iterations",
  max_parallel_agents: "Parallel agents",
  max_searches_per_sub_agent: "Searches per agent",
  max_searches_per_sub_agent_ceiling: "Searches ceiling",
  max_finds_per_sub_agent: "Finds per agent",
  default_max_time_s: "Time budget (s)",
  skill_router_top_k: "Skill router top-k",
};

export default function BudgetSection() {
  const { settings, status, mutate } = useSettings();
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (!settings) {
    return (
      <SectionShell id="budget" title="Budget & limits"
        description="Effort controls how many iterations, agents and searches a run may spend.">
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const { effort, run_defaults, advanced } = settings;
  const levels = Object.keys(effort.levels) as EffortLevel[];
  const hasOverrides = Object.keys(effort.overrides).length > 0;

  const selectLevel = (level: EffortLevel) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        effort: { ...s.effort, level, knobs: { ...s.effort.levels[level] }, overrides: {} },
      }),
      call: () => putEffort(level),
      merge: (s, view) => ({ ...s, effort: view }),
      errorLabel: "Couldn't set effort",
    });

  const setKnob = (key: string, value: number) => {
    const preset = effort.levels[effort.level] ?? {};
    const overrides = { ...effort.overrides };
    if (preset[key] === value) delete overrides[key];
    else overrides[key] = value;
    return mutate({
      optimistic: (s) => ({
        ...s,
        effort: { ...s.effort, knobs: { ...s.effort.knobs, [key]: value }, overrides },
      }),
      call: () => putEffort(effort.level, overrides),
      merge: (s, view) => ({ ...s, effort: view }),
      errorLabel: "Couldn't set budget knob",
    });
  };

  const clearOverrides = () =>
    mutate({
      call: () => putEffort(effort.level),
      merge: (s, view) => ({ ...s, effort: view }),
      errorLabel: "Couldn't reset overrides",
    });

  const setDefault = (patch: { max_time_s?: number }) =>
    mutate({
      optimistic: (s) => ({ ...s, run_defaults: { ...s.run_defaults, ...patch } }),
      call: () => putMisc(patch),
      merge: (s, view) => ({
        ...s,
        run_defaults: {
          ...s.run_defaults,
          max_time_s: view.max_time_s,
          search_max_results: view.search_max_results,
          enable_skills: view.enable_skills,
        },
      }),
      errorLabel: "Couldn't save default",
    });

  // First-class runtime knobs not covered by effort (retries, search results).
  const setAdvanced = (patch: { llm_max_retries?: number; search_max_results?: number }) =>
    mutate({
      optimistic: (s) => ({ ...s, advanced: { ...s.advanced, ...patch } }),
      call: () => putAdvanced(patch),
      merge: (s, view) => ({
        ...s,
        advanced: view,
        run_defaults: { ...s.run_defaults, search_max_results: view.search_max_results },
      }),
      errorLabel: "Couldn't save limit",
    });

  const disabled = status !== "ready";

  return (
    <SectionShell id="budget" title="Budget & limits"
      description="Effort controls how many iterations, agents and searches a run may spend.">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {levels.map((level) => (
          <button
            key={level}
            type="button"
            disabled={disabled}
            aria-pressed={effort.level === level}
            onClick={() => selectLevel(level)}
            className={`rounded-xl border px-3 py-2.5 text-left transition-colors disabled:opacity-40 ${
              effort.level === level
                ? "border-accent bg-clay/40"
                : "border-line bg-surface hover:border-line-strong"
            }`}
          >
            <div className={`text-[13.5px] font-medium capitalize ${
              effort.level === level ? "text-accent-ink" : "text-ink"
            }`}>
              {level}
            </div>
            <div className="mt-0.5 text-[11.5px] leading-snug text-ink-faint">{LEVEL_HINTS[level]}</div>
          </button>
        ))}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim"
        >
          <ChevronRight size={13} className={`transition-transform duration-200 ${showAdvanced ? "rotate-90" : ""}`} />
          Advanced overrides
          {hasOverrides && <span className="ml-1 rounded-md bg-clay px-1.5 py-0.5 text-[10.5px] text-accent-ink">{Object.keys(effort.overrides).length}</span>}
        </button>
        {showAdvanced && (
          <div className="rise-in mt-2">
            <Card>
              {Object.entries(effort.knobs).map(([key, val]) => (
                <Row key={key} label={KNOB_LABELS[key] ?? key}
                  hint={key in effort.overrides ? `overrides ${effort.level} preset (${effort.levels[effort.level]?.[key]})` : undefined}>
                  <NumberField value={val} onCommit={(v) => setKnob(key, v)} disabled={disabled} />
                </Row>
              ))}
              {hasOverrides && (
                <div className="px-4 py-2.5">
                  <button
                    type="button"
                    onClick={clearOverrides}
                    className="flex items-center gap-1.5 text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim"
                  >
                    <RotateCcw size={12} /> Reset to {effort.level} preset
                  </button>
                </div>
              )}
            </Card>
          </div>
        )}
      </div>

      <Card>
        <Row label="Default time limit" hint="Wall-clock cap per search run">
          <NumberField value={run_defaults.max_time_s} onCommit={(v) => setDefault({ max_time_s: v })}
            suffix="s" disabled={disabled} />
        </Row>
        <Row label="Search results per query" hint="Max results each web search returns">
          <NumberField value={advanced.search_max_results}
            onCommit={(v) => setAdvanced({ search_max_results: v })} disabled={disabled} />
        </Row>
        <Row label="LLM retries" hint="Retries on a rate-limited / failed model call">
          <NumberField value={advanced.llm_max_retries} min={0} max={20}
            onCommit={(v) => setAdvanced({ llm_max_retries: v })} disabled={disabled} />
        </Row>
      </Card>
    </SectionShell>
  );
}
