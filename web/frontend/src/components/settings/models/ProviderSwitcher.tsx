"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, Loader2, Search } from "lucide-react";

import { getProviderPresets, putProvider } from "@/lib/api";
import type { ProviderPresetInfo, ProvidersResponse } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import SecretField from "@/components/settings/controls/SecretField";

interface Props {
  activePreset: string;
  onClose: () => void;
  onSwitched: (clearedRoleOverrides: boolean) => void;
}

const GROUP_LABELS: Record<string, string> = {
  coding_plan: "Coding plans",
  pay_as_you_go: "Pay-as-you-go APIs",
  local: "Local deployments",
};

/**
 * Inline provider setup panel (web counterpart of the CLI setup wizard):
 * pick a preset, paste the key, optionally override model / API base.
 * No optimistic update — a switch rebuilds all profiles server-side.
 */
export default function ProviderSwitcher({ activePreset, onClose, onSwitched }: Props) {
  const { mutate, status } = useSettings();
  const [data, setData] = useState<ProvidersResponse | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string>(activePreset);
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [fastModel, setFastModel] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [applying, setApplying] = useState(false);
  const [loadSeq, setLoadSeq] = useState(0); // bump to retry

  useEffect(() => {
    let alive = true;
    getProviderPresets()
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setLoadError(true); });
    return () => { alive = false; };
  }, [loadSeq]);

  const retryLoad = () => { setLoadError(false); setData(null); setLoadSeq((n) => n + 1); };

  const presets = useMemo(
    () => (data ? data.groups.flatMap((g) => g.presets) : []),
    [data],
  );
  const preset: ProviderPresetInfo | undefined = presets.find((p) => p.name === selected);
  const q = filter.trim().toLowerCase();
  const matches = (p: ProviderPresetInfo) =>
    !q || p.name.includes(q) || p.label.toLowerCase().includes(q);

  const switching = selected !== "" && selected !== activePreset;
  const keyMissing = !!preset?.requires_key && !preset.key_set && !key.trim();
  const modelMissing = !!preset?.requires_model && !model.trim()
    && !(selected === activePreset && data?.overrides.model);
  const canApply = !!preset && !keyMissing && !modelMissing && !applying && status === "ready";

  const apply = async () => {
    if (!preset || applying) return;
    if (switching && !confirming) { setConfirming(true); return; }
    setApplying(true);
    const result = await mutate({
      call: () => putProvider({
        preset: preset.name,
        api_key: key.trim() || undefined,
        model: model.trim() || undefined,
        fast_model: fastModel.trim() || undefined,
        api_base: apiBase.trim() || undefined,
      }),
      merge: (s, r) => ({ ...s, models: r.models }),
      errorLabel: "Couldn't switch provider",
    });
    setApplying(false);
    setConfirming(false);
    if (result) {
      setKey("");
      onSwitched(result.cleared_role_overrides.length > 0);
      onClose();
    }
  };

  return (
    <div className="rise-in mt-3 space-y-3 border-t border-line pt-3">
      {/* preset picker */}
      <label className="surface flex items-center gap-2 rounded-lg px-2.5 py-1.5">
        <Search size={13} className="shrink-0 text-ink-faint" />
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter providers…"
          spellCheck={false}
          className="w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-faint"
        />
      </label>

      {loadError ? (
        <div className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2.5 text-[12.5px] text-warn">
          Couldn&apos;t load the preset list.
          <button type="button" onClick={retryLoad}
            className="text-accent-ink transition-opacity hover:opacity-80">
            Retry
          </button>
        </div>
      ) : !data ? (
        <div className="space-y-1.5">
          {[0, 1, 2].map((i) => <div key={i} className="h-9 animate-pulse rounded-lg bg-surface-2" />)}
        </div>
      ) : (
        <div className="max-h-64 space-y-2 overflow-y-auto pr-0.5">
          {data.groups.map((g) => {
            const visible = g.presets.filter(matches);
            if (!visible.length) return null;
            return (
              <div key={g.name}>
                <div className="px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                  {GROUP_LABELS[g.name] ?? g.name}
                </div>
                <div className="space-y-0.5">
                  {visible.map((p) => (
                    <button
                      key={p.name}
                      type="button"
                      onClick={() => { setSelected(p.name); setConfirming(false); }}
                      className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors ${
                        selected === p.name ? "bg-clay/60" : "hover:bg-surface-2"
                      }`}
                    >
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${p.key_set ? "bg-ok" : "bg-line-strong"}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] text-ink">{p.label}</span>
                        <span className="block truncate font-mono text-[11px] text-ink-faint">{p.name}</span>
                      </span>
                      {p.name === activePreset && <Check size={13} className="shrink-0 text-accent-ink" />}
                      {p.doc_url && (
                        <a href={p.doc_url} target="_blank" rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Docs for ${p.name}`}
                          className="shrink-0 text-ink-faint transition-colors hover:text-ink-dim">
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* detail area */}
      {preset && (
        <div className="space-y-2.5">
          {preset.notes && (
            <p className="text-[12px] leading-relaxed text-ink-faint">{preset.notes}</p>
          )}

          {preset.requires_model && (
            <div>
              <div className="mb-1 text-[12px] text-ink-dim">
                Model <span className="text-warn">Required</span>
              </div>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={data?.overrides.model || "e.g. qwen3:32b"}
                spellCheck={false}
                className="surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[13px] text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent"
              />
            </div>
          )}

          <div>
            <div className="mb-1 text-[12px] text-ink-dim">
              API key {!preset.requires_key && <span className="text-ink-faint">(optional — local server)</span>}
              <span className="ml-1.5 font-mono text-[11px] text-ink-faint">{preset.api_key_env}</span>
            </div>
            <SecretField
              value={key}
              onChange={setKey}
              disabled={applying}
              placeholder={preset.key_set ? "Configured — leave blank to keep" : "Paste API key"}
              ariaLabel={`API key (${preset.api_key_env})`}
            />
          </div>

          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            className="text-[12px] text-ink-faint transition-colors hover:text-ink-dim"
          >
            {advancedOpen ? "Hide advanced overrides" : "Advanced overrides…"}
          </button>
          {advancedOpen && (
            <div className="rise-in space-y-2">
              {!preset.requires_model && (
                <input value={model} onChange={(e) => setModel(e.target.value)}
                  placeholder={`Model (default: ${preset.main_model})`} spellCheck={false}
                  className="surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[13px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent" />
              )}
              <input value={fastModel} onChange={(e) => setFastModel(e.target.value)}
                placeholder={`Fast model (default: ${preset.fast_model || preset.main_model || "same as model"})`}
                spellCheck={false}
                className="surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[13px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent" />
              <input value={apiBase} onChange={(e) => setApiBase(e.target.value)}
                placeholder={`API base (default: ${preset.api_base || "SDK default"})`} spellCheck={false}
                className="surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[13px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent" />
            </div>
          )}

          {/* footer */}
          {confirming ? (
            <div className="flex items-center justify-between gap-3 rounded-lg bg-surface-2 px-3 py-2.5">
              <span className="text-[12.5px] text-ink-dim">
                Switching rebuilds all model profiles and clears role overrides.
              </span>
              <span className="flex shrink-0 gap-2">
                <button type="button" onClick={() => setConfirming(false)}
                  className="text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim">
                  Cancel
                </button>
                <button type="button" onClick={apply} disabled={!canApply}
                  className="flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-[12.5px] text-white transition-opacity hover:opacity-90 disabled:opacity-25">
                  {applying && <Loader2 size={12} className="animate-spin" />} Confirm switch
                </button>
              </span>
            </div>
          ) : (
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} disabled={applying}
                className="rounded-lg px-3 py-1.5 text-[13px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
                Cancel
              </button>
              <button type="button" onClick={apply} disabled={!canApply}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[13px] text-white transition-opacity hover:opacity-90 disabled:opacity-25">
                {applying && <Loader2 size={13} className="animate-spin" />}
                {switching ? "Switch provider" : "Apply"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
