"use client";

import { useWorkspaceBase } from "@/hooks/useWorkspaceBase";

import Link from "next/link";
import { ArrowLeft, Blocks, WifiOff } from "lucide-react";
import { useSettings } from "@/components/settings/SettingsProvider";
import SkillCreationPanel from "./SkillCreationPanel";

export default function SkillCreationPage() {
  const base = useWorkspaceBase();
  const { status, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1360px] px-4 py-6 sm:px-8 sm:py-8">
      <Link href={`${base}/skills`} className="mb-6 inline-flex items-center gap-1.5 rounded-lg py-2 text-[13px] text-ink-dim hover:text-ink">
        <ArrowLeft size={14} />{zh ? "返回技能库" : "Back to skills"}
      </Link>
      <header className="mb-7">
        <div className="mb-4 flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-accent-ink"><Blocks size={14} /> SEARCHOS SKILLS</div>
        <div className="mb-3 text-ink">
          <h1 className="text-[28px] font-semibold tracking-tight sm:text-[32px]">{zh ? "技能创建" : "Create a skill"}</h1>
        </div>
        <p className="text-[13px] text-ink-dim">
          {zh ? "从一个需求出发，跟踪研究、开发与独立验收，让每次修复都有迹可循。" : "Turn a request into a reusable skill. Follow research, development, verification and every repair."}
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
