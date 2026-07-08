"use client";

import { useState } from "react";
import { Loader2, Plus } from "lucide-react";

import { createProfile } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";

const PROVIDERS = ["openai_compatible", "openai", "anthropic"];

const inputCls =
  "surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent disabled:opacity-40";

/** Dashed "add" card that expands into a custom-profile creation form. */
export default function NewProfileCard({ disabled = false }: { disabled?: boolean }) {
  const { mutate } = useSettings();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("openai_compatible");
  const [apiBase, setApiBase] = useState("");
  const [keyEnv, setKeyEnv] = useState("");

  const canCreate = name.trim() !== "" && model.trim() !== "" && keyEnv.trim() !== "" && !busy;

  const create = async () => {
    if (!canCreate) return;
    setBusy(true);
    const result = await mutate({
      call: () => createProfile({
        name: name.trim(), model: model.trim(), provider,
        api_base: apiBase.trim(), api_key_env: keyEnv.trim(),
      }),
      merge: (s, models) => ({ ...s, models }),
      errorLabel: "Couldn't create profile",
    });
    setBusy(false);
    if (result) {
      setOpen(false);
      setName(""); setModel(""); setProvider("openai_compatible"); setApiBase(""); setKeyEnv("");
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className="flex min-h-24 items-center justify-center gap-1.5 rounded-xl border border-dashed border-line text-[12.5px] text-ink-faint transition-colors hover:border-line-strong hover:text-ink-dim disabled:opacity-40"
      >
        <Plus size={14} /> New profile
      </button>
    );
  }

  return (
    <div className="surface rounded-xl px-3.5 py-3">
      <div className="text-[12.5px] text-ink">New profile</div>
      <div className="mt-2 space-y-1.5">
        <input value={name} onChange={(e) => setName(e.target.value)} disabled={busy}
          placeholder="Name (e.g. my-vllm)" aria-label="Profile name" spellCheck={false} className={inputCls} />
        <input value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}
          placeholder="Model (e.g. Qwen3-32B)" aria-label="Model" spellCheck={false} className={inputCls} />
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          disabled={busy}
          aria-label="Protocol"
          className="surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors focus:border-accent disabled:opacity-40"
        >
          {PROVIDERS.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
        <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} disabled={busy}
          placeholder="API base (empty = SDK default)" aria-label="API base" spellCheck={false} className={inputCls} />
        <input value={keyEnv} onChange={(e) => setKeyEnv(e.target.value.toUpperCase())} disabled={busy}
          placeholder="API key env var (e.g. MY_VLLM_KEY)" aria-label="API key env var"
          spellCheck={false} className={inputCls} />
        <div className="flex justify-end gap-2 pt-0.5">
          <button type="button" onClick={() => setOpen(false)} disabled={busy}
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
