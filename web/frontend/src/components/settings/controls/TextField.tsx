"use client";

import { useEffect, useState, type KeyboardEvent } from "react";

interface Props {
  value: string;
  onCommit: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  mono?: boolean;
}

/** Draft-state text input: commits on blur/Enter, Escape reverts. Non-secret
 *  (value is shown in full) — for API keys use SecretField/KeyEditor instead. */
export default function TextField({
  value, onCommit, disabled = false, placeholder, mono = true,
}: Props) {
  const [draft, setDraft] = useState(value);

  useEffect(() => { setDraft(value); }, [value]);

  const commit = () => {
    if (draft === value) return;
    onCommit(draft.trim());
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); (e.target as HTMLInputElement).blur(); }
    if (e.key === "Escape") setDraft(value);
  };

  return (
    <input
      type="text"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={onKey}
      disabled={disabled}
      placeholder={placeholder}
      className={`surface w-full min-w-0 rounded-lg px-2.5 py-1.5 text-[13px] text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent disabled:opacity-40 ${
        mono ? "font-mono text-[12px]" : ""
      }`}
    />
  );
}
