"use client";

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
}

export default function SectionNav({ active, onSelect }: Props) {
  return (
    <nav className="flex flex-col gap-0.5">
      {SECTIONS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => onSelect(id)}
          className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors ${
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
