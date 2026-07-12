"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, RotateCcw, WifiOff } from "lucide-react";

import { resetSettings } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import SectionNav, { SECTIONS, type SectionId } from "@/components/settings/SectionNav";
import BudgetSection from "@/components/settings/sections/BudgetSection";
import ExperimentalSection from "@/components/settings/sections/ExperimentalSection";
import SkillsSection from "@/components/settings/sections/SkillsSection";
import ModelsSection from "@/components/settings/sections/ModelsSection";
import SearchSection from "@/components/settings/sections/SearchSection";
import AppearanceSection from "@/components/settings/sections/AppearanceSection";

export default function SettingsPage() {
  const { status, refresh, mutate } = useSettings();
  const [active, setActive] = useState<SectionId>(SECTIONS[0].id);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => { refresh(); }, [refresh]);

  const scrollTo = (id: SectionId) => {
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const doReset = () =>
    mutate({
      call: () => resetSettings(),
      merge: (_s, data) => data,
      errorLabel: "Couldn't reset settings",
    }).finally(() => setConfirmReset(false));

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[880px] gap-8 px-6 py-8">
      <aside className="sticky top-8 hidden h-fit w-44 shrink-0 lg:block">
        <Link href="/"
          className="mb-4 flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-[13px] text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink">
          <ArrowLeft size={14} /> Back
        </Link>
        <SectionNav active={active} onSelect={scrollTo} />
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mb-6 flex items-center justify-between lg:hidden">
          <Link href="/" className="flex items-center gap-1.5 text-[13px] text-ink-dim hover:text-ink">
            <ArrowLeft size={14} /> Back
          </Link>
        </div>
        <h1 className="font-serif text-[24px] text-ink">Settings</h1>

        {status === "offline" && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-warn/10 px-4 py-2.5 text-[13px] text-warn">
            <WifiOff size={14} />
            Backend offline — settings can&apos;t be loaded. Retrying…
          </div>
        )}

        <div className="mt-8 space-y-10 pb-16">
          <ModelsSection />
          <SearchSection />
          <SkillsSection />
          <BudgetSection />
          <ExperimentalSection />
          <AppearanceSection />

          <section className="border-t border-line pt-6">
            {confirmReset ? (
              <span className="flex items-center gap-3 text-[13px]">
                <span className="text-ink-dim">Reset all web settings to env defaults?</span>
                <button type="button" onClick={doReset}
                  className="rounded-lg bg-err px-3 py-1.5 text-white transition-opacity hover:opacity-90">
                  Reset
                </button>
                <button type="button" onClick={() => setConfirmReset(false)}
                  className="rounded-lg px-3 py-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
                  Cancel
                </button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmReset(true)} disabled={status !== "ready"}
                className="flex items-center gap-1.5 text-[13px] text-ink-faint transition-colors hover:text-err disabled:opacity-40">
                <RotateCcw size={13} /> Reset all settings
              </button>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
