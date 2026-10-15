"use client";

import { useWorkspaceBase } from "@/hooks/useWorkspaceBase";

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
import QuickSetupSection from "@/components/settings/sections/QuickSetupSection";

export default function SettingsPage() {
  const base = useWorkspaceBase();
  const { status, refresh, mutate, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
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
    <div className="mobile-settings mx-auto flex min-h-screen w-full max-w-[880px] gap-8 px-6 py-8">
      <aside className="sticky top-8 hidden h-fit w-44 shrink-0 lg:block">
        <Link href={base || "/"}
          className="mb-4 flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-[13px] text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink">
          <ArrowLeft size={14} /> {zh ? "返回" : "Back"}
        </Link>
        <SectionNav active={active} onSelect={scrollTo} />
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mb-6 flex items-center justify-between lg:hidden">
          <Link href={base || "/"} className="flex items-center gap-1.5 text-[13px] text-ink-dim hover:text-ink">
            <ArrowLeft size={14} /> {zh ? "返回" : "Back"}
          </Link>
        </div>
        <h1 className="font-serif text-[24px] text-ink">{zh ? "设置" : "Settings"}</h1>
        <label className="mt-4 flex items-center gap-3 text-sm text-ink-dim lg:hidden">
          {zh ? "跳转分区" : "Jump to section"}
          <select aria-label={zh ? "设置分区" : "Settings section"} value={active} onChange={(event) => scrollTo(event.target.value as SectionId)} className="min-w-0 flex-1 rounded-lg border border-line bg-surface p-3">
            {SECTIONS.map(section => <option key={section.id} value={section.id}>{zh ? ({ setup: "快速配置", models: "模型", search: "联网与读取", skills: "技能", budget: "预算与限制", experimental: "研究策略", appearance: "外观" }[section.id]) : section.label}</option>)}
          </select>
        </label>

        {status === "offline" && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-warn/10 px-4 py-2.5 text-[13px] text-warn">
            <WifiOff size={14} />
            {zh ? "后端未连接，暂时无法读取设置，正在重试…" : "Backend offline — settings can't be loaded. Retrying…"}
          </div>
        )}

        <div className="mt-8 space-y-10 pb-16">
          <QuickSetupSection onNavigate={scrollTo} />
          <ModelsSection />
          <SearchSection />
          <SkillsSection />
          <BudgetSection />
          <ExperimentalSection />
          <AppearanceSection />

          <section className="border-t border-line pt-6">
            {confirmReset ? (
              <span className="settings-reset-confirmation flex items-center gap-3 text-[13px]">
                <span className="text-ink-dim">{zh ? "将全部网页设置恢复为环境变量默认值？" : "Reset all web settings to environment defaults?"}</span>
                <button type="button" onClick={doReset}
                  className="rounded-lg bg-err px-3 py-1.5 text-white transition-opacity hover:opacity-90">
                  {zh ? "重置" : "Reset"}
                </button>
                <button type="button" onClick={() => setConfirmReset(false)}
                  className="rounded-lg px-3 py-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
                  {zh ? "取消" : "Cancel"}
                </button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmReset(true)} disabled={status !== "ready"}
                className="flex items-center gap-1.5 text-[13px] text-ink-faint transition-colors hover:text-err disabled:opacity-40">
                <RotateCcw size={13} /> {zh ? "重置全部设置" : "Reset all settings"}
              </button>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
