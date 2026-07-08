"use client";

import { useState } from "react";
import { Loader2, Pencil, RotateCcw, Trash2 } from "lucide-react";

import { deleteProfile, patchProfile } from "@/lib/api";
import type { ProfileInfo } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import KeyEditor from "@/components/settings/models/KeyEditor";

interface Props {
  name: string;
  profile: ProfileInfo;
  disabled?: boolean;
}

const inputCls =
  "surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent disabled:opacity-40";

/**
 * One model profile. Connection fields (model / api_base / api_key_env) are
 * editable inline — base profiles get web overrides (resettable), custom
 * profiles are edited in place and can be deleted when no role binds them.
 */
export default function ProfileCard({ name, profile: p, disabled = false }: Props) {
  const { mutate } = useSettings();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [keyEnv, setKeyEnv] = useState("");

  const startEdit = () => {
    setModel(p.model);
    setApiBase(p.api_base);
    setKeyEnv(p.api_key_env);
    setEditing(true);
    setConfirmDelete(false);
  };

  const call = async (fn: () => Promise<import("@/lib/types").ModelsView>, errorLabel: string) => {
    setBusy(true);
    const result = await mutate({
      call: fn,
      merge: (s, models) => ({ ...s, models }),
      errorLabel,
    });
    setBusy(false);
    return result;
  };

  const save = async () => {
    const patch: { model?: string; api_base?: string; api_key_env?: string } = {};
    const drafts = { model: model.trim(), api_base: apiBase.trim(), api_key_env: keyEnv.trim() };
    if (drafts.model && drafts.model !== p.model) patch.model = drafts.model;
    if (drafts.api_base !== p.api_base) patch.api_base = drafts.api_base;
    if (drafts.api_key_env && drafts.api_key_env !== p.api_key_env) patch.api_key_env = drafts.api_key_env;
    if (!Object.keys(patch).length) { setEditing(false); return; }
    // On a base profile "" would mean "clear override" — an empty api_base
    // draft equal to the base value is filtered out above, so "" only goes
    // through when the user actually emptied a previously-set base.
    if (await call(() => patchProfile(name, patch), "Couldn't update profile")) setEditing(false);
  };

  const reset = () =>
    call(() => patchProfile(name, { model: "", api_base: "", api_key_env: "" }),
      "Couldn't reset profile");

  const remove = async () => {
    if (await call(() => deleteProfile(name), "Couldn't delete profile")) setConfirmDelete(false);
  };

  return (
    <div className="surface rounded-xl px-3.5 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-mono text-[12.5px] text-ink">{name}</span>
          {p.custom && (
            <span className="shrink-0 rounded-md bg-clay px-1.5 py-0.5 text-[10px] text-accent-ink">custom</span>
          )}
          {p.overridden.length > 0 && (
            <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">edited</span>
          )}
        </span>
        <span className={`flex shrink-0 items-center gap-1.5 text-[11px] ${p.api_key_set ? "text-ok" : "text-warn"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${p.api_key_set ? "bg-ok" : "bg-warn"}`} />
          {p.api_key_set ? "Key configured" : "No API key"}
        </span>
      </div>

      {editing ? (
        <div className="mt-2 space-y-1.5">
          <input value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}
            placeholder="Model" aria-label={`Model for ${name}`} spellCheck={false} className={inputCls} />
          <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} disabled={busy}
            placeholder="API base (empty = SDK default)" aria-label={`API base for ${name}`}
            spellCheck={false} className={inputCls} />
          <input value={keyEnv} onChange={(e) => setKeyEnv(e.target.value.toUpperCase())} disabled={busy}
            placeholder="API key env var" aria-label={`API key env for ${name}`}
            spellCheck={false} className={inputCls} />
          <div className="flex justify-end gap-2 pt-0.5">
            <button type="button" onClick={() => setEditing(false)} disabled={busy}
              className="text-[12px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
              Cancel
            </button>
            <button type="button" onClick={save} disabled={busy}
              className="flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-[12px] text-white transition-opacity hover:opacity-90 disabled:opacity-25">
              {busy && <Loader2 size={11} className="animate-spin" />} Save
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-1.5 space-y-0.5 text-[11.5px] text-ink-faint">
          <div className="truncate">model: <span className="text-ink-dim">{p.model}</span></div>
          <div className="truncate">provider: {p.provider}</div>
          <div className="truncate">base: {p.api_base || "SDK default"}</div>
          <div className="truncate">key env: <span className="font-mono">{p.api_key_env}</span></div>
        </div>
      )}

      {!editing && (
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="flex items-center gap-3">
            <button type="button" onClick={startEdit} disabled={disabled}
              className="flex items-center gap-1 text-[11.5px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40">
              <Pencil size={11} /> Edit
            </button>
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
          </span>
          {!p.api_key_set && <KeyEditor envName={p.api_key_env} keySet={false} disabled={disabled} />}
        </div>
      )}
    </div>
  );
}
