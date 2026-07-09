"use client";

import { useEffect, useRef } from "react";
import { RotateCcw } from "lucide-react";

import type { EffortLevel } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import NumberField from "@/components/settings/controls/NumberField";
import PillGroup from "@/components/settings/controls/PillGroup";

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
  // Each effort level bundles a wall-clock budget (default_max_time_s) —
  // switching effort snaps the time limit to that level's budget.
  const levelTime = (lvl: string): number | undefined =>
    settings?.effort?.levels?.[lvl as EffortLevel]?.default_max_time_s;

  return (
    <div
      ref={ref}
      className={`rise-in surface absolute left-0 z-30 w-80 rounded-xl p-3.5 shadow-xl ${
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
            className="flex items-center gap-1 text-[12px] text-ink-faint transition-colors hover:text-ink-dim"
          >
            <RotateCcw size={11} /> Reset
          </button>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink">Effort</span>
          <PillGroup
            value={overrides.effort ?? "default"}
            options={EFFORT_OPTIONS}
            onChange={(v) =>
              setOverrides(
                v === "default"
                  ? {}
                  : { effort: v as EffortLevel, max_time: levelTime(v) },
              )
            }
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink">Time limit</span>
          <NumberField
            value={overrides.max_time ?? defaults?.max_time_s ?? 1800}
            placeholder={defaults ? String(defaults.max_time_s) : undefined}
            suffix="s"
            onCommit={(v) =>
              setOverrides({
                ...overrides,
                max_time: v === defaults?.max_time_s ? undefined : v,
              })
            }
          />
        </div>
      </div>
    </div>
  );
}
