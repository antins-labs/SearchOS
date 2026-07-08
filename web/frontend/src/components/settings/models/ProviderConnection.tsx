"use client";

import { useState } from "react";
import { X } from "lucide-react";

import type { ModelsView } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import KeyEditor from "@/components/settings/models/KeyEditor";
import ProviderSwitcher from "@/components/settings/models/ProviderSwitcher";

/** The profile whose key represents the connection: orchestrator's, else the first. */
function primaryProfile(models: ModelsView) {
  const name = models.roles["orchestrator"] ?? Object.keys(models.profiles)[0];
  return name ? models.profiles[name] : undefined;
}

/**
 * First card of the Models section: which provider preset is live, its key
 * status, and the entry point into the provider switcher.
 */
export default function ProviderConnection() {
  const { settings, status } = useSettings();
  const [open, setOpen] = useState(false);
  const [overridesNote, setOverridesNote] = useState(false);

  if (!settings) return null;
  const { models } = settings;
  const disabled = status !== "ready";
  const profile = primaryProfile(models);
  const keySet = profile?.api_key_set ?? false;

  return (
    <div className="surface rounded-xl px-4 py-3.5">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${keySet ? "bg-ok" : "bg-warn"}`} />
            <span className="truncate text-[13.5px] text-ink">
              {models.active_provider_preset
                ? <span className="font-mono">{models.active_provider_preset}</span>
                : "Built-in defaults"}
            </span>
          </div>
          {profile && (
            <div className="mt-0.5 truncate text-[12px] text-ink-faint">
              main model: <span className="font-mono text-ink-dim">{profile.model || "—"}</span>
            </div>
          )}
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={() => { setOpen((v) => !v); setOverridesNote(false); }}
          className={`shrink-0 rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors disabled:opacity-40 ${
            open ? "border-line-strong text-ink-dim" : "border-line text-ink-dim hover:border-line-strong"
          }`}
        >
          {open ? "Close" : "Change provider"}
        </button>
      </div>

      {!open && !keySet && profile && (
        <div className="mt-2 flex items-center justify-between gap-3 rounded-lg bg-surface-2 px-3 py-2">
          <span className="text-[12px] text-warn">
            {profile.api_key_env} is not set — runs will fail
          </span>
          <KeyEditor envName={profile.api_key_env} keySet={false} disabled={disabled} />
        </div>
      )}

      {!open && overridesNote && (
        <div className="rise-in mt-2 flex items-center justify-between gap-3 text-[12px] text-ink-faint">
          Role overrides were reset to the preset defaults.
          <button type="button" aria-label="Dismiss" onClick={() => setOverridesNote(false)}
            className="text-ink-faint transition-colors hover:text-ink-dim">
            <X size={12} />
          </button>
        </div>
      )}

      {open && (
        <ProviderSwitcher
          activePreset={models.active_provider_preset}
          onClose={() => setOpen(false)}
          onSwitched={(cleared) => setOverridesNote(cleared)}
        />
      )}
    </div>
  );
}
