"use client";

import { useMemo, useState } from "react";
import { Loader2, Pencil, RotateCcw, Trash2 } from "lucide-react";

import { deleteProfile, patchProfile } from "@/lib/api";
import type { ModelsView, ProfileInfo } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import Toggle from "@/components/settings/controls/Toggle";
import Select from "@/components/ui/Select";

interface Props {
  name: string;
  profile: ProfileInfo;
  disabled?: boolean;
}

const inputCls =
  "surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent disabled:opacity-40";

/**
 * One model card. Its provider comes from a user-defined provider connection
 * (chosen via the dropdown) — picking one inherits protocol/base/key/thinking
 * from it, so the card itself only edits a model id, temperature and thinking
 * (plus, when the connection carries several keys, which key to use). The API
 * key VALUE is managed on the connection, never here. Base profiles keep an
 * "env default" option; custom profiles can be deleted.
 */
export default function ProfileCard({ name, profile: p, disabled = false }: Props) {
  const { settings, mutate } = useSettings();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const [model, setModel] = useState("");
  const [temp, setTemp] = useState("");
  const [rpm, setRpm] = useState("0");
  const [tpm, setTpm] = useState("0");
  const [enableThinking, setEnableThinking] = useState(false);
  const [providerRef, setProviderRef] = useState("");  // "" = env default / inline
  const [keyEnv, setKeyEnv] = useState("");             // which of the connection's keys

  const conns = useMemo(
    () => settings?.models.provider_connections ?? {},
    [settings?.models.provider_connections],
  );
  const connNames = Object.keys(conns);
  const selConn = providerRef ? conns[providerRef] : undefined;
  const keyChoices = selConn?.api_key_envs ?? [];
  const primaryEnv = keyChoices[0]?.env ?? "";

  // Thinking is only controllable when the connection defines HOW to spell the
  // switch (thinking_style != none). At "none" the backend sends no thinking
  // param and the model falls back to its own default (reasoning models default
  // ON), so the toggle would be a silent no-op.
  const effProtocol = selConn ? selConn.protocol : p.provider;
  const effThinkingStyle = selConn ? selConn.thinking_style : p.thinking_style;
  const thinkingControllable = effProtocol !== "anthropic" && effThinkingStyle !== "none";

  const startEdit = () => {
    setModel(p.model);
    setTemp(p.temperature === null ? "" : String(p.temperature));
    setRpm(String(p.rpm));
    setTpm(String(p.tpm));
    setEnableThinking(p.enable_thinking);
    setProviderRef(p.provider_ref ?? "");
    setKeyEnv(p.api_key_env);
    setEditing(true);
    setConfirmDelete(false);
  };

  // Switching connection invalidates the old key pick — fall back to its default.
  const onProviderRef = (ref: string) => {
    setProviderRef(ref);
    setKeyEnv(ref ? (conns[ref]?.api_key_envs[0]?.env ?? "") : "");
  };

  const call = async (fn: () => Promise<ModelsView>, errorLabel: string) => {
    setBusy(true);
    const result = await mutate({ call: fn, merge: (s, models) => ({ ...s, models }), errorLabel });
    setBusy(false);
    return result;
  };

  const tempValid = temp.trim() === "" || !Number.isNaN(Number(temp));
  const quotaValue = (value: string) => value.trim() === "" ? 0 : Number(value);
  const quotaValid = (value: string) => Number.isSafeInteger(quotaValue(value)) && quotaValue(value) >= 0;
  const limitsValid = quotaValid(rpm) && quotaValid(tpm);

  const save = async () => {
    const patch: Parameters<typeof patchProfile>[1] = {};
    const draftModel = model.trim();
    if (draftModel && draftModel !== p.model) patch.model = draftModel;

    const curRef = p.provider_ref ?? "";
    if (providerRef !== curRef) {
      patch.provider_ref = providerRef;  // "" clears the ref
      // Realign the key selection to the new connection ("" = its default key).
      patch.api_key_env = providerRef ? (keyEnv === primaryEnv ? "" : keyEnv) : "";
    } else if (providerRef && keyEnv !== p.api_key_env) {
      patch.api_key_env = keyEnv === primaryEnv ? "" : keyEnv;
    }

    const newTemp = temp.trim() === "" ? null : Number(temp);
    if (newTemp !== p.temperature) patch.temperature = newTemp;

    const newRpm = quotaValue(rpm);
    const newTpm = quotaValue(tpm);
    if (newRpm !== p.rpm) patch.rpm = newRpm;
    if (newTpm !== p.tpm) patch.tpm = newTpm;

    const thinkingOn = thinkingControllable ? enableThinking : p.enable_thinking;
    if (thinkingOn !== p.enable_thinking) patch.enable_thinking = thinkingOn;

    if (!Object.keys(patch).length) { setEditing(false); return; }
    if (await call(() => patchProfile(name, patch), "Couldn't update model")) setEditing(false);
  };

  // Clear every web override for a base profile (connection + sampling + model).
  const reset = () =>
    call(() => patchProfile(name, {
      model: "", api_base: "", api_key_env: "", provider_ref: "", temperature: null,
      rpm: null, tpm: null,
    }), "Couldn't reset model");

  const remove = async () => {
    if (await call(() => deleteProfile(name), "Couldn't delete model")) setConfirmDelete(false);
  };

  const refLabel = useMemo(() => {
    if (!p.provider_ref) return p.custom ? "manual (inline)" : "env default";
    return conns[p.provider_ref]?.label || p.provider_ref;
  }, [p.provider_ref, p.custom, conns]);

  return (
    <div className="surface rounded-xl px-4 py-3.5">
      <div className="flex items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${p.api_key_set ? "bg-ok" : "bg-warn"}`} />
          <span className="truncate font-mono text-[13px] text-ink">{name}</span>
          {p.custom && (
            <span className="shrink-0 rounded-md bg-clay px-1.5 py-0.5 text-[10px] text-accent-ink">custom</span>
          )}
          {p.overridden.length > 0 && (
            <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">edited</span>
          )}
        </span>
        {!editing && (
          <button type="button" onClick={startEdit} disabled={disabled}
            className="flex shrink-0 items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-ink-dim transition-colors hover:border-line-strong disabled:opacity-40">
            <Pencil size={12} /> Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="mt-2 space-y-1.5">
          <label className="block">
            <span className="mb-1 block text-[11px] text-ink-faint">Provider</span>
            <Select
              value={providerRef}
              onChange={onProviderRef}
              disabled={busy}
              ariaLabel={`Provider for ${name}`}
              className="w-full"
              options={[
                { value: "", label: p.custom ? "Manual (inline)" : "Env default" },
                ...connNames.map((connectionName) => ({
                  value: connectionName,
                  label: conns[connectionName].label || connectionName,
                })),
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
                ariaLabel={`API key for ${name}`}
                className="w-full"
                monospace
                options={keyChoices.map((key) => ({
                  value: key.env,
                  label: `${key.env}${key.env === primaryEnv ? " (default)" : ""}${key.key_set ? "" : " - not set"}`,
                }))}
              />
            </label>
          )}
          {connNames.length === 0 && (
            <p className="text-[11px] text-ink-faint">
              No provider connections yet — add one in Providers above to switch.
            </p>
          )}
          <input value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}
            placeholder="Model id" aria-label={`Model for ${name}`} spellCheck={false} className={inputCls} />
          <input value={temp} onChange={(e) => setTemp(e.target.value)} disabled={busy}
            placeholder="Temperature (empty = omit)" aria-label={`Temperature for ${name}`}
            inputMode="decimal" spellCheck={false}
            className={`${inputCls} ${tempValid ? "" : "border-err"}`} />
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-[11px] text-ink-faint">RPM</span>
              <input value={rpm} onChange={(e) => setRpm(e.target.value)} disabled={busy}
                placeholder="0 = unlimited" aria-label={`RPM for ${name}`} inputMode="numeric" spellCheck={false}
                className={`${inputCls} ${quotaValid(rpm) ? "" : "border-err"}`} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] text-ink-faint">TPM</span>
              <input value={tpm} onChange={(e) => setTpm(e.target.value)} disabled={busy}
                placeholder="0 = unlimited" aria-label={`TPM for ${name}`} inputMode="numeric" spellCheck={false}
                className={`${inputCls} ${quotaValid(tpm) ? "" : "border-err"}`} />
            </label>
          </div>
          <p className="text-[10.5px] text-ink-faint">Per-minute quota shared by profiles using the same endpoint, model, and API key. 0 disables the limit.</p>
          {effProtocol !== "anthropic" && (thinkingControllable ? (
            <div className="flex items-center justify-between py-0.5">
              <span className="text-[12px] text-ink-dim">Thinking</span>
              <Toggle checked={enableThinking} disabled={busy} label={`Thinking for ${name}`}
                onChange={setEnableThinking} />
            </div>
          ) : (
            <p className="text-[11px] text-ink-faint">
              连接 thinking_style=none — 未定义 thinking 开关，运行时跟随模型默认（推理模型通常默认开）。
              到 Providers 给该连接设置 thinking 方式后，此处才可开关。
            </p>
          ))}
          <div className="flex justify-end gap-2 pt-0.5">
            <button type="button" onClick={() => setEditing(false)} disabled={busy}
              className="text-[12px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
              Cancel
            </button>
            <button type="button" onClick={save} disabled={busy || !tempValid || !limitsValid}
              className="flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-[12px] text-white transition-opacity hover:opacity-90 disabled:opacity-25">
              {busy && <Loader2 size={11} className="animate-spin" />} Save
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-1.5 space-y-0.5 text-[11.5px] text-ink-faint">
            <div className="truncate">model: <span className="text-ink-dim">{p.model}</span></div>
            <div className="truncate">provider: <span className="font-mono">{refLabel}</span> · {p.provider}</div>
            <div className="truncate">key env: <span className="font-mono">{p.api_key_env}</span></div>
            <div className="truncate">
              temperature: {p.temperature === null ? "omitted" : p.temperature}
            </div>
            <div className="truncate">
              quota: <span className="text-ink-dim">{p.rpm || "unlimited"} RPM · {p.tpm || "unlimited"} TPM</span>
            </div>
            <div className="truncate">
              thinking: {p.thinking_style === "none"
                ? "跟随模型默认" : (p.enable_thinking ? "on" : "off")}
            </div>
          </div>
          {(p.overridden.length > 0 || p.custom) && (
            <div className="mt-2 flex items-center gap-3">
              {p.overridden.length > 0 && (
                <button type="button" onClick={reset} disabled={disabled || busy}
                  className="flex items-center gap-1 text-[11.5px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
                  <RotateCcw size={11} /> Reset
                </button>
              )}
              {p.custom && (confirmDelete ? (
                <span className="flex items-center gap-2 text-[11.5px]">
                  <span className="text-err">Delete?</span>
                  <button type="button" onClick={remove} disabled={busy}
                    className="text-err transition-opacity hover:opacity-80 disabled:opacity-40">Yes</button>
                  <button type="button" onClick={() => setConfirmDelete(false)}
                    className="text-ink-faint transition-colors hover:text-ink-dim">No</button>
                </span>
              ) : (
                <button type="button" onClick={() => setConfirmDelete(true)} disabled={disabled}
                  className="flex items-center gap-1 text-[11.5px] text-ink-faint transition-colors hover:text-err disabled:opacity-40">
                  <Trash2 size={11} /> Delete
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
