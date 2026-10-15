"use client";

import { useSettings } from "@/components/settings/SettingsProvider";
import Composer, { type SubmitOpts } from "@/components/shell/Composer";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";

interface Props {
  onSubmit: (q: string, opts: SubmitOpts) => void;
  error?: string | null;
  localLibrary: LocalLibraryController;
}

const SUGGESTIONS = [
  { label: "Wide table", text: "Compare the top GPU cloud providers on price, regions, and SLA" },
  { label: "Enumerate", text: "List every Fields Medalist since 2000 with institution and country" },
  { label: "Timeline", text: "Which EU countries banned single-use plastics, and when?" },
  { label: "Deep dive", text: "Find the exact amount and date of Anthropic's latest funding round" },
];

export default function Landing({ onSubmit, error, localLibrary }: Props) {
  const { uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const suggestions = zh ? [
    { label: "多维对比", text: "对比主流 GPU 云服务商的价格、覆盖地区和 SLA" },
    { label: "完整枚举", text: "列出 2000 年以来的菲尔兹奖得主、所属机构与国家" },
    { label: "时间脉络", text: "哪些欧盟国家禁止了一次性塑料，分别从何时开始？" },
    { label: "深入研究", text: "查证 Anthropic 最近一轮融资的金额、日期与原始来源" },
  ] : SUGGESTIONS;
  return (
    <div className="research-landing flex h-full min-h-0 flex-col items-center overflow-y-auto px-4 pb-8 pt-20 sm:px-6 min-[1180px]:py-8">
      <div className="w-full max-w-2xl shrink-0 min-[1180px]:my-auto">
        <h1 className="wordmark rise-in mb-3 text-center text-5xl tracking-tight sm:text-7xl">SearchOS</h1>
        <p className="research-landing-subtitle rise-in mb-7 text-center text-[21px] font-medium tracking-tight text-ink sm:mb-9 sm:text-[25px]"
          style={{ animationDelay: "40ms" }}>
          {zh ? "今天，我们研究什么？" : "What will we research today?"}
        </p>

        {/* relative z-20: the rise-in animation (fill: both) makes this and the
            suggestion grid below persistent stacking contexts, so without an
            explicit order the composer's popovers paint underneath the cards. */}
        <div className="rise-in relative z-20" style={{ animationDelay: "80ms" }}>
          <Composer onSubmit={onSubmit} localLibrary={localLibrary} variant="hero" />
        </div>

        {error && <p className="mt-3 text-center text-[13px] text-err">{error}</p>}

        <div className="research-suggestions rise-in mt-5 grid grid-cols-1 gap-2.5 sm:grid-cols-2" style={{ animationDelay: "140ms" }}>
          {suggestions.map((s) => (
            <button
              type="button"
              key={s.text}
              disabled={localLibrary.mode === "local" && !localLibrary.selection}
              onClick={() => onSubmit(s.text, { sources: localLibrary.selection })}
              className="surface group flex flex-col gap-1 rounded-xl px-4 py-3 text-left transition-colors hover:border-line-strong hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent-ink">{s.label}</span>
              <span className="line-clamp-2 text-[13.5px] leading-snug text-ink-dim group-hover:text-ink">{s.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
