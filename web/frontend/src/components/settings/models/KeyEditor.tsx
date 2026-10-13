"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";

import { putSettingsKey } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import SecretField from "@/components/settings/controls/SecretField";

interface Props {
  envName: string;
  keySet: boolean;
  disabled?: boolean;
  /** Tighter layout for profile cards. */
  compact?: boolean;
}

/**
 * Self-saving key editor. The plaintext draft lives only in local state and
 * is cleared on save, cancel, and unmount — it never enters settings state.
 */
export default function KeyEditor({ envName, keySet, disabled = false, compact = false }: Props) {
  const { mutate, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (savedTimer.current) clearTimeout(savedTimer.current); }, []);

  const save = async () => {
    const value = draft.trim();
    if (!value || saving) return;
    setSaving(true);
    const result = await mutate({
      call: () => putSettingsKey(envName, value),
      merge: (s, models) => ({ ...s, models }),
      errorLabel: zh ? "无法保存密钥" : "Couldn't save key",
    });
    setSaving(false);
    if (result) {
      setDraft("");
      setSaved(true);
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => { setSaved(false); setOpen(false); }, 2000);
    }
  };

  if (saved) {
    return (
      <span className="flex items-center gap-1 text-[12px] text-ok">
        <Check size={12} /> {zh ? "密钥已保存" : "Key saved"}
      </span>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className={`text-[12px] transition-colors disabled:opacity-40 ${
          keySet ? "text-ink-faint hover:text-ink-dim" : "text-accent-ink hover:opacity-80"
        }`}
      >
        {keySet ? (zh ? "编辑" : "Edit") : (zh ? "添加密钥" : "Add key")}
      </button>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${compact ? "mt-1.5" : ""}`}>
      <SecretField
        value={draft}
        onChange={setDraft}
        onCommit={save}
        disabled={saving}
        placeholder={keySet ? (zh ? `${envName} 的新值` : `New value for ${envName}`) : envName}
        ariaLabel={`API key for ${envName}`}
      />
      <button
        type="button"
        onClick={save}
        disabled={saving || !draft.trim()}
        className="flex shrink-0 items-center gap-1 rounded-lg bg-accent px-2.5 py-1.5 text-[12px] text-white transition-opacity hover:opacity-90 disabled:opacity-25"
      >
        {saving && <Loader2 size={12} className="animate-spin" />} {zh ? "保存" : "Save"}
      </button>
      <button
        type="button"
        onClick={() => { setDraft(""); setOpen(false); }}
        disabled={saving}
        className="shrink-0 text-[12px] text-ink-faint transition-colors hover:text-ink-dim disabled:opacity-40"
      >
        {zh ? "取消" : "Cancel"}
      </button>
    </div>
  );
}
