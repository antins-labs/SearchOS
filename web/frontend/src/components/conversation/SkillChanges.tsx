"use client";

import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUpRight, Blocks, ChevronDown, Loader2, Plus, RefreshCw } from "lucide-react";
import { useSkillGeneration } from "@/hooks/useSkillGeneration";
import { useWorkspaceBase } from "@/hooks/useWorkspaceBase";
import { useSettings } from "@/components/settings/SettingsProvider";
import type { GeneratedSkill } from "@/lib/types";

export default function SkillChanges({ sessionId, generationId }: { sessionId: string | null; generationId?: string | null }) {
  const { data, error, retry } = useSkillGeneration(sessionId, generationId);
  const base = useWorkspaceBase();
  const { uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  if (!sessionId || !generationId) return null;

  const pending = !data || data.status === "queued" || data.status === "running";
  const added = data?.items.filter((item) => item.status === "installed" && item.action === "create").length ?? 0;
  const updated = data?.items.filter((item) => item.status === "installed" && item.action === "update").length ?? 0;
  const summary = pending
    ? (data?.items.length ? (zh ? "正在生成并验证技能…" : "Building and validating skills…") : (zh ? "正在整理可复用的技能…" : "Looking for reusable skills…"))
    : data.status === "interrupted" ? (zh ? "技能生成已中断，已保存的变化保留在下方。" : "Generation was interrupted. Saved changes are shown below.")
      : data.status === "error" ? (zh ? "技能生成未完成，搜索结果已保留。" : "Skill generation did not finish. Your search results are saved.")
        : !data.items.length ? (zh ? "本轮未发现需要新增或更新的技能。" : "No skills needed to be added or updated this run.")
          : !added && !updated ? (zh ? "本轮没有技能通过验证，技能库未变更。" : "No skills passed validation. The library is unchanged.")
            : (zh ? `已新增 ${added} 个技能，更新 ${updated} 个技能。` : `${added} skills added, ${updated} updated.`);

  return <section className="my-5 min-w-0 rounded-2xl border border-line bg-surface p-4" aria-label={zh ? "本轮技能变化" : "Skill changes this run"}>
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div className="flex min-w-0 items-center gap-2"><Blocks size={16} className="shrink-0 text-accent-ink" /><h3 className="text-[13px] font-semibold text-ink">{zh ? "技能变化" : "Skill changes"}</h3>{pending && !error && <Loader2 size={14} className="animate-spin text-ink-faint" />}</div>
      <Link href={`${base}/skills`} className="ml-auto inline-flex items-center gap-1 rounded text-[11px] text-ink-dim hover:text-accent-ink">{zh ? "技能库" : "Skill library"}<ArrowUpRight size={13} /></Link>
    </header>
    <p role="status" className="mt-2 text-[12px] leading-5 text-ink-dim">{summary}</p>
    {error && <p className="mt-2 text-[12px] text-warn">{zh ? "暂时无法同步技能变化，正在重试。" : "Unable to sync skill changes. Retrying."}<button type="button" onClick={retry} className="ml-2 rounded underline">{zh ? "立即重试" : "Retry now"}</button></p>}
    {!!data?.items.length && <ul className="mt-3 divide-y divide-line border-t border-line">
      {data.items.map((item, index) => <SkillChange key={`${index}:${item.category}/${item.name}`} item={item} pending={pending} zh={zh} />)}
    </ul>}
  </section>;
}

function SkillChange({ item, pending, zh }: { item: GeneratedSkill; pending: boolean; zh: boolean }) {
  const installed = item.status === "installed";
  const working = pending && (item.status === "pending" || item.status === "running");
  const label = installed ? (item.action === "update" ? (zh ? "已更新" : "Updated") : (zh ? "已新增" : "Added"))
    : working ? (item.status === "running" ? (zh ? "生成中" : "Building") : (zh ? "待生成" : "Queued"))
      : (zh ? "未入库" : "Not installed");
  return <li className="min-w-0 py-3 last:pb-0">
    <div className="flex flex-wrap items-start gap-2">
      <span className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] ${installed ? "bg-accent/10 text-accent-ink" : "bg-surface-2 text-ink-faint"}`}>
        {installed ? item.action === "update" ? <RefreshCw size={10} /> : <Plus size={10} /> : null}{label}
      </span>
      <span className="min-w-0 flex-1 break-all text-[12px] font-medium leading-5 text-ink">{item.name}</span>
      <span className="text-[10px] leading-5 text-ink-faint">{item.category}</span>
    </div>
    {item.description && <p className="mt-1.5 break-words text-[12px] leading-5 text-ink-dim">{item.description}</p>}
    {item.reason && <p className="mt-1 break-words text-[11px] leading-5 text-ink-faint">{zh ? "变化原因：" : "Reason: "}{item.reason}</p>}
    {installed && item.body && <details className="group mt-2">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded py-1 text-[11px] text-accent-ink [&::-webkit-details-marker]:hidden">{zh ? "查看本次版本" : "View this version"}<ChevronDown size={12} className="transition-transform group-open:rotate-180" /></summary>
      <div className="mt-2 max-h-80 overflow-auto rounded-xl bg-paper p-3 text-[12px] leading-6 text-ink-dim [overflow-wrap:anywhere] [&_h1]:mb-3 [&_h1]:font-semibold [&_h2]:mt-3 [&_h2]:font-semibold [&_li]:ml-4 [&_ol]:list-decimal [&_pre]:whitespace-pre-wrap [&_table]:block [&_table]:overflow-auto [&_ul]:list-disc">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          img: ({ alt }) => <span>{alt}</span>,
          a: ({ href, children }) => href && /^https?:\/\//.test(href)
            ? <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent-ink underline">{children}</a>
            : <span>{children}</span>,
        }}>{item.body}</ReactMarkdown>
      </div>
    </details>}
    {installed && !item.body && <p className="mt-2 text-[11px] text-ink-faint">{zh ? "本次版本预览不可用，可前往技能库查看当前版本。" : "This version preview is unavailable. Visit the library for the current version."}</p>}
    {!installed && !working && <p className="mt-1.5 text-[11px] text-warn">{item.status === "validation_failed" ? (zh ? "未通过验证，未修改技能库。" : "Validation failed; the library was not changed.") : (zh ? "生成未完成，未修改技能库。" : "Generation did not finish; the library was not changed.")}</p>}
  </li>;
}
