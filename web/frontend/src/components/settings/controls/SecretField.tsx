"use client";

import type { KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  /** Enter commits; Escape clears the draft. */
  onCommit?: () => void;
}

/**
 * Write-only secret input. The value is never readable back from the server
 * (responses only carry key_set booleans), so there is no show/hide toggle —
 * revealing would only expose the local draft.
 */
export default function SecretField({
  value, onChange, placeholder, disabled = false, ariaLabel, onCommit,
}: Props) {
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); onCommit?.(); }
    if (e.key === "Escape") onChange("");
  };

  return (
    <input
      type="password"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKey}
      disabled={disabled}
      placeholder={placeholder}
      aria-label={ariaLabel}
      autoComplete="off"
      spellCheck={false}
      className="surface w-full rounded-lg px-2.5 py-1.5 font-mono text-[13px] text-ink outline-none transition-colors placeholder:font-sans placeholder:text-ink-faint focus:border-accent disabled:opacity-40"
    />
  );
}
