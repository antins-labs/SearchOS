"use client";

import { useMemo, useState } from "react";
import { ChevronRight, Search } from "lucide-react";

import { patchSkill, putMisc, putSkillCategory, putSkills } from "@/lib/api";
import type { SkillsView } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import { OfflineSkeleton, SectionShell } from "@/components/settings/primitives";
import Toggle from "@/components/settings/controls/Toggle";
import NumberField from "@/components/settings/controls/NumberField";

const BIG_GROUP = 40; // groups larger than this start collapsed (TUI parity)

export default function SkillsSection() {
  const { settings, status, mutate, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const [filter, setFilter] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const categories = useMemo(
    () => Object.entries(settings?.skills.categories ?? {}),
    [settings],
  );

  if (!settings) {
    return (
      <SectionShell id="skills" title={zh ? "技能" : "Skills"}
        description={zh ? "管理编排器和子智能体可以使用的技能。" : "Manage skills available to the orchestrator and sub-agents."}>
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const disabled = status !== "ready";
  const q = filter.trim().toLowerCase();

  const mergeSkills = (s: typeof settings, view: SkillsView) => ({ ...s, skills: view });

  const toggleSkill = (cat: string, name: string, enabled: boolean) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        skills: {
          ...s.skills,
          categories: {
            ...s.skills.categories,
            [cat]: s.skills.categories[cat].map((sk) =>
              sk.name === name ? { ...sk, enabled } : sk),
          },
        },
      }),
      call: () => patchSkill(name, enabled),
      merge: mergeSkills,
      errorLabel: "Couldn't toggle skill",
    });

  const toggleCategory = (cat: string, enabled: boolean) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        skills: {
          ...s.skills,
          categories: {
            ...s.skills.categories,
            [cat]: s.skills.categories[cat].map((sk) => ({ ...sk, enabled })),
          },
        },
      }),
      call: () => putSkillCategory(cat, enabled),
      merge: mergeSkills,
      errorLabel: "Couldn't toggle category",
    });

  const toggleSkillsSystem = (enabled: boolean) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        skills: { ...s.skills, enable_skills: enabled },
        run_defaults: { ...s.run_defaults, enable_skills: enabled },
      }),
      call: () => putMisc({ enable_skills: enabled }),
      errorLabel: "Couldn't toggle skills system",
    });

  const toggleAccessGeneration = (enabled: boolean) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        skills: { ...s.skills, enable_access_skill_generation: enabled },
      }),
      call: () => putSkills({ enable_access_skill_generation: enabled }),
      merge: mergeSkills,
      errorLabel: "Couldn't toggle access-skill generation",
    });

  const setAccessGenerationMax = (count: number) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        skills: { ...s.skills, access_skill_max_per_run: count },
      }),
      call: () => putSkills({ access_skill_max_per_run: count }),
      merge: mergeSkills,
      errorLabel: "Couldn't update access-skill generation limit",
    });

  return (
    <SectionShell id="skills" title={zh ? "技能" : "Skills"}
      description={zh ? "管理编排器和子智能体可以使用的技能。" : "Manage skills available to the orchestrator and sub-agents."}>
      <div className="flex items-center justify-between gap-3">
        <label className="surface flex min-w-0 flex-1 items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-ink-faint">
          <Search size={14} />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={zh ? "筛选技能…" : "Filter skills…"}
            spellCheck={false}
            className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
          />
        </label>
        <span className="flex shrink-0 items-center gap-2 text-[12.5px] text-ink-dim">
          {zh ? "启用技能" : "Enable skills"}
          <Toggle checked={settings.skills.enable_skills} disabled={disabled} label={zh ? "启用技能" : "Enable skills"}
            onChange={toggleSkillsSystem} />
        </span>
      </div>

      <div className="surface flex items-center justify-between gap-4 rounded-xl px-3 py-2.5">
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-ink">{zh ? "任务后学习技能" : "Learn skills after tasks"}</div>
          <div className="text-[11.5px] text-ink-faint">{zh ? "根据轨迹新增或更新访问、检索策略和编排技能，验证后供后续任务使用。" : "Create or update access, strategy and orchestrator skills from traces after validation."}</div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="flex items-center gap-1.5 text-[12px] text-ink-dim">
            {zh ? "上限" : "Max"}
            <NumberField
              value={settings.skills.access_skill_max_per_run}
              min={1}
              max={10}
              onCommit={setAccessGenerationMax}
              disabled={disabled || !settings.skills.enable_access_skill_generation}
            />
          </span>
          <Toggle
            checked={settings.skills.enable_access_skill_generation}
            disabled={disabled}
            label={zh ? "任务后学习技能" : "Learn skills after tasks"}
            onChange={toggleAccessGeneration}
          />
        </div>
      </div>

      {categories.every(([, skills]) => skills.length === 0) ? (
        <p className="text-[13px] text-ink-faint">
          {zh ? "未找到技能；技能库可能已停用或为空。" : "No skills found; the skill library may be disabled or empty."}
        </p>
      ) : (
        <div className="space-y-2">
          {categories.map(([cat, skills]) => {
            const shown = q
              ? skills.filter((s) =>
                  s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q))
              : skills;
            const enabledCount = skills.filter((s) => s.enabled).length;
            const isCollapsed = q
              ? shown.length === 0
              : (collapsed[cat] ?? skills.length > BIG_GROUP);
            if (q && shown.length === 0) return null;
            return (
              <div key={cat} className="surface rounded-xl">
                <div className="flex items-center justify-between px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => setCollapsed((c) => ({ ...c, [cat]: !isCollapsed }))}
                    className="flex min-w-0 items-center gap-1.5 text-left"
                  >
                    <ChevronRight size={13}
                      className={`shrink-0 text-ink-faint transition-transform duration-200 ${isCollapsed ? "" : "rotate-90"}`} />
                    <span className="text-[13px] font-medium text-ink">{cat}</span>
                    <span className="text-[12px] tabular-nums text-ink-faint">
                      {enabledCount}/{skills.length}
                    </span>
                  </button>
                  <span className="flex shrink-0 items-center gap-1 text-[12px]">
                    <button type="button" disabled={disabled} onClick={() => toggleCategory(cat, true)}
                      className="rounded-md px-1.5 py-0.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink disabled:opacity-40">
                      {zh ? "全部开启" : "All on"}
                    </button>
                    <button type="button" disabled={disabled} onClick={() => toggleCategory(cat, false)}
                      className="rounded-md px-1.5 py-0.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink disabled:opacity-40">
                      {zh ? "全部关闭" : "All off"}
                    </button>
                  </span>
                </div>
                {!isCollapsed && (
                  <div className="max-h-80 overflow-y-auto border-t border-line">
                    {shown.map((sk) => (
                      <div key={sk.name} className="flex items-center justify-between gap-3 px-3 py-2">
                        <div className="min-w-0">
                          <div className={`truncate font-mono text-[12.5px] ${sk.enabled ? "text-ink" : "text-ink-faint"}`}>
                            {sk.name}
                            <span className="ml-2 font-sans text-[11px] text-ink-faint">
                              {sk.package_format === "portable"
                                ? (zh ? "通用技能" : "Portable")
                                : (zh ? "旧版兼容" : "Legacy")}
                            </span>
                          </div>
                          {sk.description && (
                            <div className="truncate text-[11.5px] text-ink-faint">{sk.description}</div>
                          )}
                        </div>
                        <Toggle checked={sk.enabled} disabled={disabled} label={sk.name}
                          onChange={(v) => toggleSkill(cat, sk.name, v)} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {settings.skills.access_mode === "only" && (
        <p className="text-[12px] text-ink-faint">
          {zh ? "访问技能已固定为显式集合；恢复全部技能后才会重新使用查询路由。" : "Access skills are pinned to an explicit set; query routing resumes after all are re-enabled."}
        </p>
      )}
    </SectionShell>
  );
}
