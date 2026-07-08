"use client";

import { useEffect, useState, type KeyboardEvent } from "react";

interface Props {
  value: number;
  onCommit: (v: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
  suffix?: string;
  placeholder?: string;
}

/** Draft-state numeric input: commits on blur/Enter, Escape reverts. */
export default function NumberField({
  value, onCommit, min = 1, max, disabled = false, suffix, placeholder,
}: Props) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => { setDraft(String(value)); }, [value]);

  const parsed = Number(draft);
  const invalid = draft !== "" && (!Number.isInteger(parsed) || parsed < min || (max != null && parsed > max));

  const commit = () => {
    if (draft === "" || invalid || parsed === value) {
      setDraft(String(value));
      return;
    }
    onCommit(parsed);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); (e.target as HTMLInputElement).blur(); }
    if (e.key === "Escape") setDraft(String(value));
  };

  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        type="text"
        inputMode="numeric"
        value={draft}
        onChange={(e) => setDraft(e.target.value.replace(/[^\d]/g, ""))}
        onBlur={commit}
        onKeyDown={onKey}
        disabled={disabled}
        placeholder={placeholder}
        className={`surface w-20 rounded-lg px-2.5 py-1.5 text-right font-mono text-[13px] tabular-nums text-ink outline-none transition-colors placeholder:text-ink-faint disabled:opacity-40 ${
          invalid ? "border-err" : "focus:border-accent"
        }`}
      />
      {suffix && <span className="text-[12px] text-ink-faint">{suffix}</span>}
    </span>
  );
}
