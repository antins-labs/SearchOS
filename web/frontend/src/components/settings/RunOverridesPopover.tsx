"use client";

import { useEffect, useRef } from "react";
import { Clock3, RotateCcw, Search, Users } from "lucide-react";

import type { EffortLevel } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import NumberField from "@/components/settings/controls/NumberField";
import PillGroup from "@/components/settings/controls/PillGroup";
import { estimateRunBudget } from "@/lib/budgetEstimate";

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

export default function RunOverridesPopover({ direction, onClose }: Props) {
  const { settings, overrides, setOverrides, clearOverrides } = useSettings();
  const ref = useRef<HTMLDivElement>(null);

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

  return (
    <div
      ref={ref}
      className={`rise-in surface absolute left-0 z-30 w-80 rounded-xl p-3.5 shadow-xl ${overrides.effort === "max" ? "max-effort-popover" : ""} ${
        direction === "down" ? "top-full mt-2" : "bottom-full mb-2"
      }`}
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[12px] font-medium uppercase tracking-wider text-ink-faint">
          This run only
        </span>
        {(overrides.effort || overrides.max_time != null) && (
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
                <div className="text-[9.5px] text-ink-faint">searches / wave</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
