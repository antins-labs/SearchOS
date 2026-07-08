"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, WifiOff, X } from "lucide-react";

import { useSettings } from "@/components/settings/SettingsProvider";
import SectionNav, { SECTIONS } from "@/components/settings/SectionNav";
import BudgetSection from "@/components/settings/sections/BudgetSection";
import SkillsSection from "@/components/settings/sections/SkillsSection";
import ModelsSection from "@/components/settings/sections/ModelsSection";
import AppearanceSection from "@/components/settings/sections/AppearanceSection";

const BODIES: Record<string, React.ComponentType> = {
  budget: BudgetSection,
  skills: SkillsSection,
  models: ModelsSection,
  appearance: AppearanceSection,
};

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const { status, refresh } = useSettings();
  const [active, setActive] = useState(SECTIONS[0].id);

  // Cheap consistency with other clients (TUI, another tab) editing config.
  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const Body = BODIES[active];

  return (
    <div className="fade-in fixed inset-0 z-40 flex items-center justify-center bg-ink/20 dark:bg-black/50"
      onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        onMouseDown={(e) => e.stopPropagation()}
        className="rise-in surface flex h-[min(620px,85vh)] w-[min(860px,92vw)] flex-col overflow-hidden rounded-2xl shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h1 className="font-serif text-[16px] text-ink">Settings</h1>
          <button type="button" onClick={onClose} aria-label="Close settings"
            className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>

        {status === "offline" && (
          <div className="flex items-center gap-2 border-b border-line bg-warn/10 px-5 py-2 text-[12.5px] text-warn">
            <WifiOff size={13} />
            Backend offline — settings can&apos;t be loaded. Retrying…
          </div>
        )}

        <div className="flex min-h-0 flex-1">
          <div className="flex w-44 shrink-0 flex-col justify-between border-r border-line p-3">
            <SectionNav active={active} onSelect={setActive} />
            <Link href="/settings" onClick={onClose}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-[12px] text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
              <ExternalLink size={13} /> Full settings
            </Link>
          </div>
          <div className="min-w-0 flex-1 overflow-y-auto p-5">
            <Body />
          </div>
        </div>
      </div>
    </div>
  );
}
