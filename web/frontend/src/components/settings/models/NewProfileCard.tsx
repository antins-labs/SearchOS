"use client";

import { useState } from "react";
import { Loader2, Plus } from "lucide-react";

import { createProfile } from "@/lib/api";
import type { ModelsView } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import Toggle from "@/components/settings/controls/Toggle";
import Select from "@/components/ui/Select";

const inputCls =
  "surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent disabled:opacity-40";
const NAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/;

/**
 * Dashed "add" card. A model card points at a provider connection and only
 * carries a model id + sampling; the connection supplies protocol/base/key.
 */
export default function NewProfileCard({ disabled = false }: { disabled?: boolean }) {
  const { settings, mutate } = useSettings();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const [providerRef, setProviderRef] = useState("");
  const [keyEnv, setKeyEnv] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [temp, setTemp] = useState("");
  const [enableThinking, setEnableThinking] = useState(false);

  const conns = settings?.models.provider_connections ?? {};
  const connNames = Object.keys(conns);
  const profiles = settings?.models.profiles ?? {};

  const selConn = providerRef ? conns[providerRef] : undefined;
  const keyChoices = selConn?.api_key_envs ?? [];
  const primaryEnv = keyChoices[0]?.env ?? "";
  const effProtocol = selConn ? selConn.protocol : "openai_compatible";
  // Thinking only controllable when the connection spells out the switch.
  const effThinkingStyle = selConn?.thinking_style ?? "none";
  const thinkingControllable = effProtocol !== "anthropic" && effThinkingStyle !== "none";

  const onProviderRef = (ref: string) => {
    setProviderRef(ref);
    setKeyEnv(ref ? (conns[ref]?.api_key_envs[0]?.env ?? "") : "");
  };

  const tempValid = temp.trim() === "" || !Number.isNaN(Number(temp));
  const nameOk = NAME_RE.test(name.trim()) && !(name.trim() in profiles);
  const canCreate = nameOk && model.trim() !== "" && providerRef !== "" && tempValid && !busy;

  const reset = () => {
    setProviderRef(""); setKeyEnv(""); setName(""); setModel(""); setTemp(""); setEnableThinking(false);
  };

  const create = async () => {
    if (!canCreate) return;
    setBusy(true);
    const result = await mutate({
      call: () => createProfile({
        name: name.trim(), model: model.trim(), provider_ref: providerRef,
        // "" (or the default key) lets the connection's default key stand.
        api_key_env: keyEnv && keyEnv !== primaryEnv ? keyEnv : undefined,
        temperature: temp.trim() === "" ? null : Number(temp),
        enable_thinking: thinkingControllable && enableThinking,
      }),
      merge: (s, models: ModelsView) => ({ ...s, models }),
      errorLabel: "Couldn't create model",
    });
    setBusy(false);
    if (result) { setOpen(false); reset(); }
  };

  if (!open) {
    return (
      <button type="button" disabled={disabled} onClick={() => setOpen(true)}
        className="flex min-h-24 items-center justify-center gap-1.5 rounded-xl border border-dashed border-line text-[12.5px] text-ink-faint transition-colors hover:border-line-strong hover:text-ink-dim disabled:opacity-40">
        <Plus size={14} /> New model
      </button>
    );
  }

  return (
    <div className="surface rounded-xl px-3.5 py-3">
      <div className="text-[12.5px] text-ink">New model</div>
      <div className="mt-2 space-y-1.5">
        {connNames.length === 0 ? (
          <p className="text-[12px] text-ink-faint">
            Add a provider connection in Providers above first, then a model can point at it.
          </p>
        ) : (
          <>
            <label className="block">
              <span className="mb-1 block text-[11px] text-ink-faint">Provider</span>
              <Select
                value={providerRef}
                onChange={onProviderRef}
                disabled={busy}
                ariaLabel="Provider connection"
                className="w-full"
                options={[
                  { value: "", label: "Select a provider...", disabled: true },
                  ...connNames.map((name) => ({ value: name, label: conns[name].label || name })),
                ]}
              />
            </label>
            {keyChoices.length > 1 && (
              <label className="block">
                <span className="mb-1 block text-[11px] text-ink-faint">API key</span>
                <Select
                  value={keyEnv}
                  onChange={setKeyEnv}
                  disabled={busy}
                  ariaLabel="API key"
                  className="w-full"
                  monospace
                  options={keyChoices.map((key) => ({
                    value: key.env,
                    label: `${key.env}${key.env === primaryEnv ? " (default)" : ""}${key.key_set ? "" : " - not set"}`,
                  }))}
                />
              </label>
            )}
            <input value={name} onChange={(e) => setName(e.target.value)} disabled={busy}
              placeholder="Name (e.g. antchat-qwen)" aria-label="Model name" spellCheck={false} className={inputCls} />
            <input value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}
              placeholder="Model id (e.g. qwen3-max)" aria-label="Model id" spellCheck={false} className={inputCls} />
            <input value={temp} onChange={(e) => setTemp(e.target.value)} disabled={busy}
              placeholder="Temperature (empty = omit)" aria-label="Temperature" inputMode="decimal"
              spellCheck={false} className={`${inputCls} ${tempValid ? "" : "border-err"}`} />
            {effProtocol !== "anthropic" && (thinkingControllable ? (
              <div className="flex items-center justify-between py-0.5">
                <span className="text-[12px] text-ink-dim">Thinking</span>
                <Toggle checked={enableThinking} disabled={busy} label="Enable thinking"
                  onChange={setEnableThinking} />
              </div>
            ) : providerRef ? (
              <p className="text-[11px] text-ink-faint">
                该连接 thinking_style=none — 运行时跟随模型默认；到 Providers 设置 thinking 方式后可开关。
              </p>
            ) : null)}
          </>
        )}
        <div className="flex justify-end gap-2 pt-0.5">
          <button type="button" onClick={() => { setOpen(false); reset(); }} disabled={busy}
            className="text-[12px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
            Cancel
          </button>
          <button type="button" onClick={create} disabled={!canCreate}
            className="flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-[12px] text-white transition-opacity hover:opacity-90 disabled:opacity-25">
            {busy && <Loader2 size={11} className="animate-spin" />} Create
          </button>
        </div>
      </div>
    </div>
  );
}
