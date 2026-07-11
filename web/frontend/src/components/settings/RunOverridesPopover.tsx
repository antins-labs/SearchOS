"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import {
  Ban,
  ChevronDown,
  Clock3,
  Globe2,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "lucide-react";

import type { EffortLevel, SkillInfo, SkillOverrides } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import NumberField from "@/components/settings/controls/NumberField";
import PillGroup from "@/components/settings/controls/PillGroup";
import { estimateRunBudget } from "@/lib/budgetEstimate";
import { EFFORT_GUIDANCE } from "@/lib/effortGuidance";

interface Props {
  /** "down" opens below the trigger (hero composer), "up" above (bottom bar). */
  direction: "down" | "up";
  onClose: () => void;
}

const EFFORT_OPTIONS = [
  { value: "default", label: "Default" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Med" },
  { value: "high", label: "High" },
  { value: "max", label: "Max" },
];

const ACCESS_MODE_OPTIONS = [
  { value: "default", label: "Default" },
  { value: "router", label: "Router" },
  { value: "only", label: "Only" },
];

type SkillCategory = "access" | "strategy" | "orchestrator";

function hasOwn(value: object | null | undefined, key: PropertyKey) {
  return value != null && Object.prototype.hasOwnProperty.call(value, key);
}

function normalizeDomain(raw: string): string {
  const value = raw.trim().toLowerCase();
  if (!value) return "";
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return url.hostname.replace(/^\*\./, "").replace(/^\.|\.$/g, "");
  } catch {
    return "";
  }
}

function DomainInput({
  label,
  icon,
  values,
  placeholder,
  onChange,
}: {
  label: string;
  icon: ReactNode;
  values: string[];
  placeholder: string;
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const additions = draft.split(/[,\s]+/).map(normalizeDomain).filter(Boolean);
    if (additions.length) onChange(Array.from(new Set([...values, ...additions])));
    setDraft("");
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="block">
      <span className="mb-1.5 flex items-center gap-1.5 text-[12px] text-ink-dim">
        {icon}
        {label}
      </span>
      <span className="flex min-h-9 flex-wrap items-center gap-1 rounded-lg border border-line bg-paper px-2 py-1.5 focus-within:border-accent/50">
        {values.map((domain) => (
          <span key={domain} className="inline-flex min-w-0 items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10.5px] text-ink">
            <span className="max-w-44 truncate">{domain}</span>
            <button
              type="button"
              aria-label={`Remove ${domain}`}
              onClick={() => onChange(values.filter((item) => item !== domain))}
              className="text-ink-faint transition-colors hover:text-ink"
            >
              <X size={10} />
            </button>
          </span>
        ))}
        <input
          aria-label={`${label} domain`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
          placeholder={values.length ? "Add domain" : placeholder}
          spellCheck={false}
          className="min-w-28 flex-1 bg-transparent py-0.5 text-[12px] text-ink outline-none placeholder:text-ink-faint"
        />
      </span>
    </div>
  );
}

export default function RunOverridesPopover({ direction, onClose }: Props) {
  const { settings, overrides, setOverrides, clearOverrides } = useSettings();
  const ref = useRef<HTMLDivElement>(null);
  const [popoverMaxHeight, setPopoverMaxHeight] = useState<number>();
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [skillFilter, setSkillFilter] = useState("");
  const [skillCategory, setSkillCategory] = useState<SkillCategory>("access");

  useLayoutEffect(() => {
    const updateMaxHeight = () => {
      const element = ref.current;
      if (!element) return;

      const rect = element.getBoundingClientRect();
      const viewportPadding = 16;
      const heightCap = Math.min(window.innerHeight * 0.78, 720);
      const availableHeight = direction === "down"
        ? window.innerHeight - rect.top - viewportPadding
        : rect.bottom - viewportPadding;
      setPopoverMaxHeight(Math.max(0, Math.floor(Math.min(heightCap, availableHeight))));
    };

    updateMaxHeight();
    window.addEventListener("resize", updateMaxHeight);
    return () => window.removeEventListener("resize", updateMaxHeight);
  }, [direction, skillsOpen]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const defaults = settings?.run_defaults;
  // Each effort level bundles a wall-clock budget (default_max_time_s). The
  // time field *displays* the selected level's budget, but it only becomes an
  // override (chip + request field) when the user edits it by hand — the
  // backend already applies the level's budget to an effort-only run.
  const levelTime = (lvl: string | undefined): number | undefined =>
    lvl ? settings?.effort?.levels?.[lvl as EffortLevel]?.default_max_time_s : undefined;
  const impliedTime = levelTime(overrides.effort) ?? defaults?.max_time_s ?? 1800;
  const selectedLevel = overrides.effort ?? settings?.effort.level ?? "medium";
  const estimate = settings
    ? estimateRunBudget(selectedLevel, settings.effort.levels, overrides.max_time ?? impliedTime)
    : null;
  const skillOverrides = overrides.skills;
  const accessMode = !hasOwn(skillOverrides, "access_only")
    ? "default"
    : skillOverrides?.access_only === null ? "router" : "only";
  const categories = useMemo(
    () => settings?.skills.categories ?? {},
    [settings?.skills.categories],
  );
  const categorySkills = useMemo(
    () => (categories[skillCategory] ?? []).filter((skill) => {
      const query = skillFilter.trim().toLowerCase();
      return !query || skill.name.toLowerCase().includes(query)
        || skill.description.toLowerCase().includes(query);
    }),
    [categories, skillCategory, skillFilter],
  );
  const hasOverrides = Boolean(
    overrides.effort
    || overrides.max_time != null
    || overrides.skills
    || overrides.trusted_domains?.length
    || overrides.excluded_domains?.length,
  );
  const hasSkillOrSourceOverrides = Boolean(
    overrides.skills
    || overrides.trusted_domains?.length
    || overrides.excluded_domains?.length,
  );

  const patchSkills = (patch: Partial<SkillOverrides>, remove: (keyof SkillOverrides)[] = []) => {
    const next: SkillOverrides = { ...(skillOverrides ?? {}) };
    remove.forEach((field) => delete next[field]);
    Object.assign(next, patch);
    setOverrides({
      ...overrides,
      skills: Object.keys(next).length ? next : undefined,
    });
  };

  const skillEnabled = (category: SkillCategory, skill: SkillInfo) => {
    if (category === "access" && accessMode === "only") {
      return skillOverrides?.access_only?.includes(skill.name) ?? false;
    }
    const field = category === "access" ? "access_deny" : `${category}_deny` as const;
    if (hasOwn(skillOverrides, field)) return !skillOverrides?.[field]?.includes(skill.name);
    return skill.enabled;
  };

  const setAccessMode = (mode: string) => {
    if (mode === "default") {
      patchSkills({}, ["access_only", "access_deny"]);
    } else if (mode === "router") {
      patchSkills({ access_only: null }, ["access_deny"]);
    } else {
      const selected = (categories.access ?? []).filter((skill) => skill.enabled).map((skill) => skill.name);
      patchSkills({ access_only: selected }, ["access_deny"]);
    }
  };

  const toggleSkill = (category: SkillCategory, name: string) => {
    const pool = categories[category] ?? [];
    if (category === "access" && accessMode === "only") {
      const selected = new Set(skillOverrides?.access_only ?? []);
      if (selected.has(name)) selected.delete(name); else selected.add(name);
      patchSkills({ access_only: Array.from(selected) });
      return;
    }
    const enabled = new Set(pool.filter((skill) => skillEnabled(category, skill)).map((skill) => skill.name));
    if (enabled.has(name)) enabled.delete(name); else enabled.add(name);
    const denied = pool.filter((skill) => !enabled.has(skill.name)).map((skill) => skill.name);
    if (category === "access") {
      patchSkills({ access_only: null, access_deny: denied });
    } else if (category === "strategy") {
      patchSkills({ strategy_deny: denied });
    } else {
      patchSkills({ orchestrator_deny: denied });
    }
  };

  return (
    <div
      ref={ref}
      style={popoverMaxHeight == null ? undefined : { maxHeight: popoverMaxHeight }}
      className={`rise-in surface absolute left-0 z-30 max-h-[min(78vh,720px)] w-[min(440px,calc(100vw-2rem))] overflow-y-auto overscroll-contain rounded-xl p-3.5 shadow-xl [scrollbar-gutter:stable] ${overrides.effort === "max" ? "max-effort-popover" : ""} ${
        direction === "down" ? "top-full mt-2" : "bottom-full mb-2"
      }`}
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[12px] font-medium uppercase tracking-wider text-ink-faint">
          This run only
        </span>
        {hasOverrides && (
          <button
            type="button"
            onClick={clearOverrides}
            className="flex items-center gap-1 text-[12px] text-ink-dim transition-colors hover:text-ink"
          >
            <RotateCcw size={11} /> Reset
          </button>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink">Effort</span>
          <PillGroup
            ariaLabel="Run effort"
            value={overrides.effort ?? "default"}
            options={EFFORT_OPTIONS}
            onChange={(v) =>
              setOverrides({
                ...overrides,
                effort: v === "default" ? undefined : (v as EffortLevel),
              })
            }
          />
        </div>
        <p className="-mt-1 text-[10.5px] leading-relaxed text-ink-faint">
          <span className="font-medium text-ink-dim">{EFFORT_GUIDANCE[selectedLevel].title}:</span>{" "}
          {EFFORT_GUIDANCE[selectedLevel].summary}
        </p>

        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink">Time limit</span>
          <NumberField
            value={overrides.max_time ?? impliedTime}
            placeholder={String(impliedTime)}
            suffix="s"
            onCommit={(v) =>
              setOverrides({
                ...overrides,
                max_time: v === impliedTime ? undefined : v,
              })
            }
          />
        </div>

        {estimate && (
          <div className="border-t border-line pt-3" aria-label="Estimated run budget">
            <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-ink-faint">Budget estimate</div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Clock3 className="mb-1 text-accent-ink" size={12} />
                <div className="text-[12px] font-medium tabular-nums text-ink">{Math.round(estimate.maxTimeSeconds / 60)}m</div>
                <div className="text-[9.5px] text-ink-faint">time cap</div>
              </div>
              <div>
                <Users className="mb-1 text-accent-ink" size={12} />
                <div className="text-[12px] font-medium tabular-nums text-ink">{estimate.parallelAgents}</div>
                <div className="text-[9.5px] text-ink-faint">parallel agents</div>
              </div>
              <div>
                <Search className="mb-1 text-accent-ink" size={12} />
                <div className="text-[12px] font-medium tabular-nums text-ink">~{estimate.searchesPerWave}</div>
                <div className="text-[9.5px] text-ink-faint">search() calls / wave</div>
              </div>
            </div>
          </div>
        )}

        <div className="border-t border-line pt-2">
          <button
            type="button"
            aria-expanded={skillsOpen}
            onClick={() => setSkillsOpen((value) => !value)}
            className="flex w-full items-center gap-2 py-1 text-left"
          >
            <Sparkles size={13} className="text-accent-ink" />
            <span className="text-[13px] text-ink">Skills &amp; sources</span>
            <span className="ml-auto text-[11px] text-ink-faint">
              {hasSkillOrSourceOverrides ? "Custom" : "Defaults"}
            </span>
            <ChevronDown size={14} className={`text-ink-faint transition-transform ${skillsOpen ? "rotate-180" : ""}`} />
          </button>

          {skillsOpen && (
            <div className="mt-2.5 space-y-3">
              {!settings?.skills.enable_skills ? (
                <p className="text-[12px] text-ink-faint">Skills are disabled in Settings.</p>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[12px] text-ink-dim">Access policy</span>
                    <PillGroup
                      ariaLabel="Access skill policy"
                      value={accessMode}
                      options={ACCESS_MODE_OPTIONS}
                      onChange={setAccessMode}
                    />
                  </div>

                  <div>
                    <div role="tablist" aria-label="Skill categories" className="mb-2 flex items-center gap-1 border-b border-line">
                      {(["access", "strategy", "orchestrator"] as SkillCategory[]).map((category) => {
                        const pool = categories[category] ?? [];
                        const count = pool.filter((skill) => skillEnabled(category, skill)).length;
                        return (
                          <button
                            key={category}
                            type="button"
                            role="tab"
                            aria-selected={skillCategory === category}
                            onClick={() => setSkillCategory(category)}
                            className={`border-b-2 px-2 py-1.5 text-[11.5px] capitalize transition-colors ${
                              skillCategory === category
                                ? "border-accent text-ink"
                                : "border-transparent text-ink-faint hover:text-ink"
                            }`}
                          >
                            {category} <span className="tabular-nums">{count}/{pool.length}</span>
                          </button>
                        );
                      })}
                    </div>
                    <label className="mb-1.5 flex items-center gap-2 rounded-lg border border-line bg-paper px-2.5 py-1.5">
                      <Search size={12} className="text-ink-faint" />
                      <input
                        value={skillFilter}
                        onChange={(event) => setSkillFilter(event.target.value)}
                        placeholder={`Filter ${skillCategory} skills`}
                        className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-ink-faint"
                      />
                    </label>
                    <div className="max-h-44 overflow-y-auto overscroll-contain border-y border-line [scrollbar-gutter:stable]">
                      {categorySkills.length ? categorySkills.map((skill) => (
                        <label key={skill.name} className="flex cursor-pointer items-start gap-2 border-b border-line/60 px-1 py-2 last:border-b-0 hover:bg-surface-2/60">
                          <input
                            type="checkbox"
                            checked={skillEnabled(skillCategory, skill)}
                            onChange={() => toggleSkill(skillCategory, skill.name)}
                            className="mt-0.5 h-3.5 w-3.5 accent-accent"
                          />
                          <span className="min-w-0">
                            <span className="block truncate font-mono text-[11.5px] text-ink">{skill.name}</span>
                            {skill.description && <span className="block truncate text-[10.5px] text-ink-faint">{skill.description}</span>}
                          </span>
                        </label>
                      )) : (
                        <p className="px-2 py-4 text-center text-[11.5px] text-ink-faint">No matching skills</p>
                      )}
                    </div>
                    {skillCategory === "access" && accessMode === "default" && (
                      <p className="mt-1.5 text-[10.5px] text-ink-faint">Changing a skill switches this run to Router mode.</p>
                    )}
                  </div>
                </>
              )}

              <div className="grid gap-2.5 sm:grid-cols-2">
                <DomainInput
                  label="Trusted domains"
                  icon={<ShieldCheck size={12} className="text-ok" />}
                  values={overrides.trusted_domains ?? []}
                  placeholder="example.org"
                  onChange={(values) => setOverrides({ ...overrides, trusted_domains: values.length ? values : undefined })}
                />
                <DomainInput
                  label="Excluded domains"
                  icon={<Ban size={12} className="text-err" />}
                  values={overrides.excluded_domains ?? []}
                  placeholder="spam.example"
                  onChange={(values) => setOverrides({ ...overrides, excluded_domains: values.length ? values : undefined })}
                />
              </div>
              <p className="flex items-start gap-1.5 text-[10.5px] leading-4 text-ink-faint">
                <Globe2 size={11} className="mt-0.5 shrink-0" />
                Trusted sources rank first. Excluded domains are removed from search results and cannot be opened.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
