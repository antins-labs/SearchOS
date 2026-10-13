"use client";

import Link from "next/link";
import { ArrowLeft, Blocks, WifiOff } from "lucide-react";
import { useSettings } from "@/components/settings/SettingsProvider";
import SkillCreationPanel from "./SkillCreationPanel";

export default function SkillCreationPage() {
  const { status, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1120px] px-5 py-6 sm:px-8 sm:py-8">
      <Link href="/skills" className="mb-10 inline-flex items-center gap-1.5 rounded-lg py-2 text-[13px] text-ink-dim hover:text-ink">
        <ArrowLeft size={14} />{zh ? "返回技能库" : "Back to skills"}
      </Link>
      <header className="mb-9">
        <div className="mb-4 flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-accent-ink"><Blocks size={14} /> SEARCHOS SKILLS</div>
        <div className="mb-3 text-ink">
          <h1 className="text-[28px] font-semibold tracking-tight sm:text-[32px]">{zh ? "让下一次搜索，更进一步。" : "Make your next search better."}</h1>
        </div>
        <p className="text-[13px] text-ink-dim">
          {zh ? "把网站访问能力、搜索方法和运行经验，变成可复用的技能。" : "Build reusable skills from sites, tasks, or traces. Track validation and results."}
        </p>
      </header>
      {status === "offline" && (
        <p role="status" className="mb-4 flex items-center gap-2 rounded-xl bg-warn/10 p-3 text-[13px] text-warn">
          <WifiOff size={15} />{zh ? "后端未连接，连接恢复后可继续创建。" : "Backend offline. Creation will be available after reconnecting."}
        </p>
      )}
      <SkillCreationPanel disabled={status !== "ready"} zh={zh} />
    </main>
  );
}
