"use client";

import { useRef, type KeyboardEvent } from "react";
import { Blocks, Cpu, Gauge, Globe, Palette, type LucideIcon } from "lucide-react";

export interface SectionDef {
  id: string;
  label: string;
  icon: LucideIcon;
}

export const SECTIONS: SectionDef[] = [
  { id: "models", label: "Models", icon: Cpu },
  { id: "search", label: "Search & browse", icon: Globe },
  { id: "skills", label: "Skills", icon: Blocks },
  { id: "budget", label: "Budget & limits", icon: Gauge },
  { id: "appearance", label: "Appearance", icon: Palette },
];

interface Props {
  active: string;
  onSelect: (id: string) => void;
  mode?: "navigation" | "tabs";
}

export default function SectionNav({ active, onSelect, mode = "navigation" }: Props) {
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (mode !== "tabs") return;
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % SECTIONS.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + SECTIONS.length) % SECTIONS.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = SECTIONS.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    onSelect(SECTIONS[nextIndex].id);
    buttonRefs.current[nextIndex]?.focus();
  };

  return (
    <nav role={mode === "tabs" ? "tablist" : undefined} aria-label={mode === "tabs" ? "Settings sections" : "Settings navigation"}
      className="flex min-w-0 gap-0.5 overflow-x-auto sm:flex-col sm:overflow-visible">
      {SECTIONS.map(({ id, label, icon: Icon }, index) => (
        <button
          ref={(element) => { buttonRefs.current[index] = element; }}
          key={id}
          id={mode === "tabs" ? `settings-tab-${id}` : undefined}
          type="button"
          role={mode === "tabs" ? "tab" : undefined}
          aria-selected={mode === "tabs" ? active === id : undefined}
          aria-controls={mode === "tabs" ? "settings-panel" : undefined}
          aria-current={mode === "navigation" && active === id ? "page" : undefined}
          tabIndex={mode === "tabs" && active !== id ? -1 : 0}
          onClick={() => onSelect(id)}
          onKeyDown={(event) => onKeyDown(event, index)}
          className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors sm:w-full ${
            active === id
              ? "bg-clay/60 font-medium text-accent-ink"
              : "text-ink-dim hover:bg-surface-2 hover:text-ink"
          }`}
        >
          <Icon size={15} className="shrink-0" />
          {label}
        </button>
      ))}
    </nav>
  );
}
