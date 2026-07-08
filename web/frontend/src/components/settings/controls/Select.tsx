"use client";

import { ChevronDown } from "lucide-react";

interface Option {
  value: string;
  label: string;
  disabled?: boolean;
}

interface Props {
  value: string;
  options: Option[];
  onChange: (v: string) => void;
  disabled?: boolean;
  ariaLabel?: string;
}

export default function Select({ value, options, onChange, disabled = false, ariaLabel }: Props) {
  return (
    <span className="relative inline-flex">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label={ariaLabel}
        className="surface appearance-none rounded-lg py-1.5 pl-3 pr-8 text-[13px] text-ink outline-none transition-colors focus:border-accent disabled:opacity-40"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={14}
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-faint"
      />
    </span>
  );
}
