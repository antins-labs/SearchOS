"use client";

import { useRef, type KeyboardEvent } from "react";

interface Props {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  disabled?: boolean;
  ariaLabel?: string;
}

export default function PillGroup({ value, options, onChange, disabled = false, ariaLabel = "Options" }: Props) {
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (disabled) return;
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % options.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + options.length) % options.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = options.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    onChange(options[nextIndex].value);
    buttonRefs.current[nextIndex]?.focus();
  };

  return (
    <span role="group" aria-label={ariaLabel} className={`inline-flex rounded-lg border border-line p-0.5 ${disabled ? "opacity-40" : ""}`}>
      {options.map((o, index) => (
        <button
          ref={(element) => { buttonRefs.current[index] = element; }}
          key={o.value}
          type="button"
          disabled={disabled}
          aria-pressed={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          onClick={() => onChange(o.value)}
          onKeyDown={(event) => onKeyDown(event, index)}
          className={`rounded-md px-2.5 py-1 text-[12.5px] transition-colors ${
            o.value === value
              ? "bg-clay font-medium text-accent-ink"
              : "text-ink-dim hover:bg-surface-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </span>
  );
}
