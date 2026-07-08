"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react";

import {
  deleteProviderConnection,
  getProviderPresets,
  putProviderConnection,
  putSettingsKey,
} from "@/lib/api";
import type { ModelsView, ProvidersResponse } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import KeyEditor from "@/components/settings/models/KeyEditor";
import SecretField from "@/components/settings/controls/SecretField";

const PROTOCOLS = ["openai_compatible", "openai", "anthropic"];
const THINKING_STYLES = ["none", "chat_template_kwargs", "enable_thinking"];

const inputCls =
  "surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent disabled:opacity-40";
const selectCls =
  "surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors focus:border-accent disabled:opacity-40";
const NAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/;
const ENV_RE = /^[A-Z][A-Z0-9_]{0,63}$/;

interface FormState {
  target: string;   // connection name being edited, or "" for a new one
  template: string;
  name: string;
  label: string;
  protocol: string;
  apiBase: string;
  keyEnvs: string[];
  thinkingStyle: string;
  apiKey: string;   // optional value for the first key on a new connection
}

const emptyForm = (): FormState => ({
  target: "", template: "custom", name: "", label: "", protocol: "openai_compatible",
  apiBase: "", keyEnvs: [""], thinkingStyle: "none", apiKey: "",
});

/**
 * The provider-connections manager. A connection is a named wire endpoint
 * (protocol + api_base + one or more key env vars); model cards point at one by
 * name and inherit all of it, so a card only sets a model id and sampling.
 * Presets act as templates that pre-fill a new connection. One connection can
 * hold several API keys (different quota / team) — the first is the default.
 */
export default function ProviderConnections() {
  const { settings, status, mutate } = useSettings();
  const [presets, setPresets] = useState<ProvidersResponse | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const editingNew = form?.target === "";
  useEffect(() => {
    if (!editingNew || presets) return;
    let alive = true;
    getProviderPresets().then((d) => { if (alive) setPresets(d); }).catch(() => {});
    return () => { alive = false; };
  }, [editingNew, presets]);

  const allPresets = useMemo(
    () => (presets ? presets.groups.flatMap((g) => g.presets) : []),
    [presets],
  );

  if (!settings) return null;
  const conns = settings.models.provider_connections;
  const names = Object.keys(conns);
  const disabled = status !== "ready";

  const patch = (p: Partial<FormState>) => setForm((f) => (f ? { ...f, ...p } : f));

  const openNew = () => { setForm(emptyForm()); setConfirmDelete(null); };
  const openEdit = (n: string) => {
    const c = conns[n];
    setForm({
      target: n, template: "custom", name: n, label: c.label, protocol: c.protocol,
      apiBase: c.api_base, keyEnvs: c.api_key_envs.map((k) => k.env), thinkingStyle: c.thinking_style,
      apiKey: "",
    });
    setConfirmDelete(null);
  };
  const closeForm = () => setForm(null);

  const onTemplate = (v: string) => {
    patch({ template: v });
    if (v === "custom") return;
    const p = allPresets.find((x) => x.name === v);
    if (p) {
      setForm((f) => f && {
        ...f, template: v, protocol: p.protocol, apiBase: p.api_base,
        keyEnvs: [p.api_key_env], thinkingStyle: p.thinking_style,
        name: f.name.trim() ? f.name : p.name, label: p.label,
      });
    }
  };

  const cleanEnvs = (f: FormState) => {
    const out: string[] = [];
    for (const e of f.keyEnvs.map((x) => x.trim().toUpperCase())) {
      if (e && !out.includes(e)) out.push(e);
    }
    return out;
  };

  const formValid = (f: FormState) => {
    const envs = cleanEnvs(f);
    const nameOk = f.target !== "" || (NAME_RE.test(f.name.trim()) && !names.includes(f.name.trim()));
    return nameOk && envs.length > 0 && f.keyEnvs.every((e) => !e.trim() || ENV_RE.test(e.trim().toUpperCase()));
  };

  const save = async () => {
    if (!form || !formValid(form) || busy) return;
    setBusy(true);
    const envs = cleanEnvs(form);
    const target = (form.target || form.name.trim());
    const result = await mutate({
      call: async () => {
        const v = await putProviderConnection(target, {
          protocol: form.protocol as "openai_compatible" | "openai" | "anthropic",
          api_base: form.apiBase.trim(), api_key_envs: envs,
          thinking_style: form.thinkingStyle as "chat_template_kwargs" | "enable_thinking" | "none",
          label: form.template === "custom" ? form.label : form.template,
        });
        // Write the optional key after the connection exists so the row shows green.
        if (form.target === "" && form.apiKey.trim()) return putSettingsKey(envs[0], form.apiKey.trim());
        return v;
      },
      merge: (s, models: ModelsView) => ({ ...s, models }),
      errorLabel: "Couldn't save provider connection",
    });
    setBusy(false);
    if (result) closeForm();
  };

  const remove = async (n: string) => {
    setBusy(true);
    const result = await mutate({
      call: () => deleteProviderConnection(n),
      merge: (s, models: ModelsView) => ({ ...s, models }),
      errorLabel: "Couldn't delete connection",
    });
    setBusy(false);
    if (result) setConfirmDelete(null);
  };

  const renderForm = (f: FormState) => (
    <div className="space-y-1.5">
      <div className="text-[12.5px] text-ink">{f.target ? `Edit ${f.target}` : "New connection"}</div>
      {f.target === "" && (
        <>
          <label className="block">
            <span className="mb-1 block text-[11px] text-ink-faint">Start from a preset (optional)</span>
            <select value={f.template} onChange={(e) => onTemplate(e.target.value)} disabled={busy}
              aria-label="Preset template" className={selectCls}>
              <option value="custom">Custom (manual)</option>
              {allPresets.map((p) => (
                <option key={p.name} value={p.name}>{p.label} ({p.name})</option>
              ))}
            </select>
          </label>
          <input value={f.name} onChange={(e) => patch({ name: e.target.value })} disabled={busy}
            placeholder="Connection name (e.g. my-antchat)" aria-label="Connection name"
            spellCheck={false} className={inputCls} />
        </>
      )}
      <select value={f.protocol} onChange={(e) => patch({ protocol: e.target.value })} disabled={busy}
        aria-label="Protocol" className={selectCls}>
        {PROTOCOLS.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
      <input value={f.apiBase} onChange={(e) => patch({ apiBase: e.target.value })} disabled={busy}
        placeholder="API base (empty = SDK default)" aria-label="API base"
        spellCheck={false} className={inputCls} />

      <div className="space-y-1">
        <span className="block text-[11px] text-ink-faint">API key env vars (first = default)</span>
        {f.keyEnvs.map((e, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <input value={e} disabled={busy} spellCheck={false} className={inputCls}
              aria-label={`API key env var ${i + 1}`} placeholder="e.g. ANTCHAT_API_KEY"
              onChange={(ev) => patch({
                keyEnvs: f.keyEnvs.map((x, j) => (j === i ? ev.target.value.toUpperCase() : x)),
              })} />
            {f.keyEnvs.length > 1 && (
              <button type="button" aria-label={`Remove key env ${i + 1}`} disabled={busy}
                onClick={() => patch({ keyEnvs: f.keyEnvs.filter((_, j) => j !== i) })}
                className="shrink-0 rounded-md p-1 text-ink-faint transition-colors hover:text-err disabled:opacity-40">
                <X size={13} />
              </button>
            )}
          </div>
        ))}
        <button type="button" disabled={busy} onClick={() => patch({ keyEnvs: [...f.keyEnvs, ""] })}
          className="flex items-center gap-1 text-[11.5px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
          <Plus size={11} /> Add another key
        </button>
      </div>

      {f.protocol !== "anthropic" && (
        <select value={f.thinkingStyle} onChange={(e) => patch({ thinkingStyle: e.target.value })} disabled={busy}
          aria-label="Thinking style" className={selectCls}>
          {THINKING_STYLES.map((v) => <option key={v} value={v}>thinking: {v}</option>)}
        </select>
      )}
      {f.target === "" && (
        <SecretField value={f.apiKey} onChange={(v) => patch({ apiKey: v })} disabled={busy}
          placeholder="Default key value (optional — can add later)" ariaLabel="API key value" />
      )}
      <div className="flex justify-end gap-2 pt-0.5">
        <button type="button" onClick={closeForm} disabled={busy}
          className="text-[12px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
          Cancel
        </button>
        <button type="button" onClick={save} disabled={busy || !formValid(f)}
          className="flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-[12px] text-white transition-opacity hover:opacity-90 disabled:opacity-25">
          {busy && <Loader2 size={11} className="animate-spin" />} {f.target ? "Save" : "Add"}
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-2">
      {names.length === 0 && !form && (
        <p className="text-[12px] text-ink-faint">
          No provider connections yet. Add one, then point model cards at it.
        </p>
      )}

      {names.map((n) => {
        const c = conns[n];
        const editingThis = form?.target === n;
        return (
          <div key={n} className="surface rounded-xl px-4 py-3.5">
            {editingThis ? renderForm(form) : (
              <>
                <div className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${c.key_set ? "bg-ok" : "bg-warn"}`} />
                    <span className="truncate text-[13.5px] text-ink">{c.label || n}</span>
                    {c.label && c.label !== n && (
                      <span className="shrink-0 font-mono text-[11px] text-ink-faint">{n}</span>
                    )}
                    <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">
                      {c.protocol}
                    </span>
                  </span>
                  {confirmDelete === n ? (
                    <span className="flex shrink-0 items-center gap-2 text-[11.5px]">
                      <span className="text-err">Delete?</span>
                      <button type="button" onClick={() => remove(n)} disabled={busy}
                        className="text-err transition-opacity hover:opacity-80 disabled:opacity-40">Yes</button>
                      <button type="button" onClick={() => setConfirmDelete(null)}
                        className="text-ink-faint transition-colors hover:text-ink-dim">No</button>
                    </span>
                  ) : (
                    <span className="flex shrink-0 items-center gap-1.5">
                      <button type="button" onClick={() => openEdit(n)} disabled={disabled}
                        className="flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-ink-dim transition-colors hover:border-line-strong disabled:opacity-40">
                        <Pencil size={12} /> Edit
                      </button>
                      <button type="button" onClick={() => setConfirmDelete(n)} disabled={disabled}
                        aria-label={`Delete ${n}`}
                        className="rounded-lg p-1.5 text-ink-faint transition-colors hover:text-err disabled:opacity-40">
                        <Trash2 size={13} />
                      </button>
                    </span>
                  )}
                </div>
                <div className="mt-1 truncate text-[12px] text-ink-faint">
                  base: <span className="font-mono text-ink-dim">{c.api_base || "SDK default"}</span>
                </div>
                <div className="mt-2 space-y-1">
                  {c.api_key_envs.map((k, i) => (
                    <div key={k.env} className="flex items-center justify-between gap-2 rounded-lg bg-surface-2 px-3 py-1.5">
                      <span className="flex min-w-0 items-center gap-2 text-[12px]">
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${k.key_set ? "bg-ok" : "bg-warn"}`} />
                        <span className="truncate font-mono text-ink-dim">{k.env}</span>
                        {i === 0 && c.api_key_envs.length > 1 && (
                          <span className="shrink-0 rounded bg-clay px-1 py-0.5 text-[9.5px] text-accent-ink">default</span>
                        )}
                      </span>
                      <KeyEditor envName={k.env} keySet={k.key_set} disabled={disabled} />
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        );
      })}

      {editingNew ? (
        <div className="surface rounded-xl px-4 py-3.5">{renderForm(form)}</div>
      ) : !form && (
        <button type="button" disabled={disabled} onClick={openNew}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-line py-2.5 text-[12.5px] text-ink-faint transition-colors hover:border-line-strong hover:text-ink-dim disabled:opacity-40">
          <Plus size={14} /> Add provider connection
        </button>
      )}
    </div>
  );
}
