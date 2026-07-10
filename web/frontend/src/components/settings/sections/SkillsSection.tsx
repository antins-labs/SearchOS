"use client";

import { useMemo, useState } from "react";
import { ChevronRight, Search } from "lucide-react";

import { patchSkill, putMisc, putSkillCategory } from "@/lib/api";
import type { SkillsView } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import { OfflineSkeleton, SectionShell } from "@/components/settings/primitives";
import Toggle from "@/components/settings/controls/Toggle";

const BIG_GROUP = 40; // groups larger than this start collapsed (TUI parity)

export default function SkillsSection() {
  const { settings, status, mutate } = useSettings();
  const [filter, setFilter] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const categories = useMemo(
    () => Object.entries(settings?.skills.categories ?? {}),
    [settings],
  );

  if (!settings) {
    return (
      <SectionShell id="skills" title="Skills"
        description="Enable or disable the skills injected into orchestrator and sub-agents.">
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

  return (
    <SectionShell id="skills" title="Skills"
      description="Enable or disable the skills injected into orchestrator and sub-agents.">
      <div className="flex items-center justify-between gap-3">
        <label className="surface flex min-w-0 flex-1 items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-ink-faint">
          <Search size={14} />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter skills…"
            spellCheck={false}
            className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
          />
        </label>
        <span className="flex shrink-0 items-center gap-2 text-[12.5px] text-ink-dim">
          Enable skills
          <Toggle checked={settings.skills.enable_skills} disabled={disabled} label="Enable skills"
            onChange={toggleSkillsSystem} />
        </span>
      </div>

      {categories.every(([, skills]) => skills.length === 0) ? (
        <p className="text-[13px] text-ink-faint">
          No skills found — the skill library may be disabled or empty.
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
                      All on
                    </button>
                    <button type="button" disabled={disabled} onClick={() => toggleCategory(cat, false)}
                      className="rounded-md px-1.5 py-0.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink disabled:opacity-40">
                      All off
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
          Access skills are pinned to an explicit set — the query router is bypassed until all are re-enabled.
        </p>
      )}
    </SectionShell>
  );
}
