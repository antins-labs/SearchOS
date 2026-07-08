"use client";

interface Props {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  disabled?: boolean;
}

export default function PillGroup({ value, options, onChange, disabled = false }: Props) {
  return (
    <span className={`inline-flex rounded-lg border border-line p-0.5 ${disabled ? "opacity-40" : ""}`}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 text-[12.5px] transition-colors ${
            o.value === value
              ? "bg-clay font-medium text-accent-ink"
              : "text-ink-faint hover:text-ink-dim"
          }`}
        >
          {o.label}
        </button>
      ))}
    </span>
  );
}
