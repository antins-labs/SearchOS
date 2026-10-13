"use client";

import { useState } from "react";
import { ChevronRight, RotateCcw } from "lucide-react";

import { putAdvanced, putEffort, putMisc } from "@/lib/api";
import type { EffortLevel } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import NumberField from "@/components/settings/controls/NumberField";
const KNOB_LABELS: Record<string, { zh: string; en: string }> = {
  orch_max_iterations: { zh: "编排步骤上限", en: "Orchestrator step limit" },
  max_parallel_agents: { zh: "并发智能体上限", en: "Concurrent agent limit" },
  max_searches_per_sub_agent: { zh: "单智能体默认检索次数", en: "Default searches per agent" },
  max_searches_per_sub_agent_ceiling: { zh: "单智能体检索硬上限", en: "Search hard cap per agent" },
  max_finds_per_sub_agent: { zh: "单智能体页内查找次数", en: "Find calls per agent" },
  max_skills_per_sub_agent: { zh: "单智能体技能调用次数", en: "Skill calls per agent" },
  default_max_time_s: { zh: "运行时间上限（秒）", en: "Run time limit (seconds)" },
  skill_router_top_k: { zh: "候选技能上限", en: "Candidate skill limit" },
  max_search_agents_per_session: { zh: "检索智能体总数上限", en: "Search agent session cap" },
  search_agent_no_progress_tool_limit: { zh: "单智能体连续无进展调用上限", en: "No-progress calls per agent" },
};

const KNOB_HINTS: Record<string, { zh: string; en: string }> = {
  orch_max_iterations: { zh: "编排器最多执行多少个决策和工具调用步骤。", en: "Maximum orchestrator decision and tool-call steps." },
  max_parallel_agents: { zh: "同一时间最多运行多少个子智能体。", en: "Maximum sub-agents that may run concurrently." },
  max_searches_per_sub_agent: { zh: "每个子智能体默认可执行的联网检索次数。", en: "Default web searches assigned to each sub-agent." },
  max_searches_per_sub_agent_ceiling: { zh: "任务请求更多检索次数时仍不能超过该值。", en: "Hard upper bound when a task requests more searches." },
  max_finds_per_sub_agent: { zh: "每个子智能体在已打开页面中查找文本的次数。", en: "Maximum text searches inside opened pages per agent." },
  max_skills_per_sub_agent: { zh: "每个子智能体可调用的访问技能次数。", en: "Maximum access-skill calls per agent." },
  default_max_time_s: { zh: "该档位采用的任务总时长限制。", en: "Wall-clock limit applied by this effort level." },
  skill_router_top_k: { zh: "任务开始前最多保留多少个候选技能。", en: "Maximum candidate skills retained before a run." },
  max_search_agents_per_session: { zh: "一次研究中最多创建多少个检索智能体；0 表示不限制。", en: "Maximum search agents created in one run; 0 disables the cap." },
  search_agent_no_progress_tool_limit: { zh: "单个检索智能体连续调用工具但没有新增阅读或事实后，触发收尾的次数。", en: "Finalize an agent after this many tool calls add no reading or facts." },
};

const LEVEL_COPY: Record<EffortLevel, { zh: string; en: string; zhSummary: string; enSummary: string }> = {
  low: { zh: "轻度", en: "Low", zhSummary: "事实查证、短文档和简单列表", enSummary: "Facts, short documents, and small lists" },
  medium: { zh: "中度", en: "Medium", zhSummary: "比较、资料整理和普通问答", enSummary: "Comparisons, synthesis, and everyday research" },
  high: { zh: "高度", en: "High", zhSummary: "多步问题、较多来源和较长文档", enSummary: "Multi-step questions, more sources, and longer documents" },
  max: { zh: "极高", en: "Max", zhSummary: "大型表格、困难来源和高召回任务", enSummary: "Large tables, difficult sources, and maximum recall" },
};

export default function BudgetSection() {
  const { settings, status, mutate, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (!settings) {
    return (
      <SectionShell id="budget" title={zh ? "预算与限制" : "Budget & limits"}
        description={zh ? "按任务复杂度选择档位，需要时再调整高级预算。" : "Choose an effort level, then tune advanced budgets only when needed."}>
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
          enable_explore_batch: view.enable_explore_batch,
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
    <SectionShell id="budget" title={zh ? "预算与限制" : "Budget & limits"}
      description={zh ? "按任务复杂度选择档位，需要时再调整高级预算。" : "Choose an effort level, then tune advanced budgets only when needed."}>
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
            <div className={`flex items-baseline gap-1.5 text-[13.5px] font-medium ${
              effort.level === level ? "text-accent-ink" : "text-ink"
            }`}>
              <span>{zh ? LEVEL_COPY[level].zh : LEVEL_COPY[level].en}</span>
            </div>
            <div className="mt-1 text-[11px] leading-snug text-ink-faint">{zh ? LEVEL_COPY[level].zhSummary : LEVEL_COPY[level].enSummary}</div>
          </button>
        ))}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          aria-expanded={showAdvanced}
          className="flex items-center gap-1 text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim"
        >
          <ChevronRight size={13} className={`transition-transform duration-200 ${showAdvanced ? "rotate-90" : ""}`} />
          {zh ? "高级参数" : "Advanced parameters"}
          {hasOverrides && <span className="ml-1 rounded-md bg-clay px-1.5 py-0.5 text-[10.5px] text-accent-ink">{Object.keys(effort.overrides).length}</span>}
        </button>
        {showAdvanced && (
          <div className="rise-in mt-2">
            <Card>
              <div className="border-b border-line px-4 py-2.5 text-[11px] leading-relaxed text-ink-faint">
                {zh ? "这些参数直接控制编排和工具调用预算。一般保留当前档位的默认值即可。" : "These parameters control orchestration and tool-call budgets. The selected level's defaults are usually sufficient."}
              </div>
              {Object.entries(effort.knobs).map(([key, val]) => {
                const overrideHint = key in effort.overrides
                  ? (zh ? `覆盖当前档位默认值（${effort.levels[effort.level]?.[key]}）。` : `Overrides the level default (${effort.levels[effort.level]?.[key]}).`)
                  : "";
                const label = KNOB_LABELS[key];
                const knobHint = KNOB_HINTS[key];
                return (
                  <Row key={key} label={label ? (zh ? label.zh : label.en) : key}
                    hint={[knobHint ? (zh ? knobHint.zh : knobHint.en) : "", overrideHint].filter(Boolean).join(" ") || undefined}>
                    <NumberField value={val} onCommit={(v) => setKnob(key, v)} disabled={disabled} />
                  </Row>
                );
              })}
              {hasOverrides && (
                <div className="px-4 py-2.5">
                  <button
                    type="button"
                    onClick={clearOverrides}
                    className="flex items-center gap-1.5 text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim"
                  >
                    <RotateCcw size={12} /> {zh ? "恢复当前档位默认值" : `Reset ${effort.level} defaults`}
                  </button>
                </div>
              )}
            </Card>
          </div>
        )}
      </div>

      <Card>
        <Row label={zh ? "默认时间限制" : "Default time limit"} hint={zh ? "每次研究的总时长上限" : "Wall-clock cap per research run"}>
          <NumberField value={run_defaults.max_time_s} onCommit={(v) => setDefault({ max_time_s: v })}
            suffix="s" disabled={disabled} />
        </Row>
        <Row label={zh ? "每次检索结果数" : "Search results per query"} hint={zh ? "每次联网检索最多返回多少条结果" : "Maximum results returned by each web search"}>
          <NumberField value={advanced.search_max_results}
            onCommit={(v) => setAdvanced({ search_max_results: v })} disabled={disabled} />
        </Row>
        <Row label={zh ? "模型重试次数" : "Model retries"} hint={zh ? "模型调用失败或受到限流时的重试次数" : "Retries after a failed or rate-limited model call"}>
          <NumberField value={advanced.llm_max_retries} min={0} max={20}
            onCommit={(v) => setAdvanced({ llm_max_retries: v })} disabled={disabled} />
        </Row>
      </Card>
    </SectionShell>
  );
}
