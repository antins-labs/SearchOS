"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ExternalLink, WifiOff, X } from "lucide-react";

import { useSettings } from "@/components/settings/SettingsProvider";
import SectionNav, { SECTIONS, type SectionId } from "@/components/settings/SectionNav";
import BudgetSection from "@/components/settings/sections/BudgetSection";
import SkillsSection from "@/components/settings/sections/SkillsSection";
import ModelsSection from "@/components/settings/sections/ModelsSection";
import SearchSection from "@/components/settings/sections/SearchSection";
import ExperimentalSection from "@/components/settings/sections/ExperimentalSection";
import AppearanceSection from "@/components/settings/sections/AppearanceSection";
import useDialogFocus from "@/hooks/useDialogFocus";

const BODIES: Record<SectionId, React.ComponentType> = {
  models: ModelsSection,
  search: SearchSection,
  skills: SkillsSection,
  budget: BudgetSection,
  experimental: ExperimentalSection,
  appearance: AppearanceSection,
};

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const { status, refresh } = useSettings();
  const [active, setActive] = useState<SectionId>(SECTIONS[0].id);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Cheap consistency with other clients (TUI, another tab) editing config.
  useEffect(() => { refresh(); }, [refresh]);

  useDialogFocus({ containerRef: dialogRef, initialFocusRef: closeRef, onClose });

  const Body = BODIES[active];

  return (
    <div className="fade-in fixed inset-0 z-40 flex items-center justify-center bg-ink/20 dark:bg-black/50"
      onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-dialog-title"
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        className="rise-in surface flex h-[100dvh] w-full flex-col overflow-hidden rounded-none shadow-xl sm:h-[min(620px,85vh)] sm:w-[min(860px,92vw)] sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h1 id="settings-dialog-title" className="font-serif text-[16px] text-ink">Settings</h1>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close settings"
            className="rounded-md p-1.5 text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>

        {status === "offline" && (
          <div className="flex items-center gap-2 border-b border-line bg-warn/10 px-5 py-2 text-[12.5px] text-warn">
            <WifiOff size={13} />
            Backend offline — settings can&apos;t be loaded. Retrying…
          </div>
        )}

        <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
          <div className="flex w-full shrink-0 items-center border-b border-line p-2 sm:w-44 sm:flex-col sm:items-stretch sm:justify-between sm:border-b-0 sm:border-r sm:p-3">
            <SectionNav active={active} onSelect={setActive} mode="tabs" />
            <Link href="/settings" onClick={onClose}
              className="hidden items-center gap-1.5 rounded-lg px-2.5 py-2 text-[12px] text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink sm:flex">
              <ExternalLink size={13} /> Full settings
            </Link>
          </div>
          <div id="settings-panel" role="tabpanel" aria-labelledby={`settings-tab-${active}`} tabIndex={0} key={active} className="min-w-0 flex-1 overflow-y-auto p-4 sm:p-5">
            <Body />
          </div>
        </div>
      </div>
    </div>
  );
}
