"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, Globe2, ListTree, Loader2, Route, SlidersHorizontal } from "lucide-react";
import SkillCreationHistory from "./SkillCreationHistory";
import { createSkills, listSkillCreations, type SkillCreationInput, type SkillCreationJob } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";

const active = (job: SkillCreationJob) => ["queued", "running"].includes(job.status);

export default function SkillCreationPanel({ disabled, zh }: { disabled: boolean; zh: boolean }) {
  const { refresh } = useSettings();
  const [kind, setKind] = useState<SkillCreationInput["kind"]>("site");
  const [site, setSite] = useState("");
  const [text, setText] = useState("");
  const [categories, setCategories] = useState(["access", "strategy", "orchestrator"]);
  const [max, setMax] = useState(3);
  const [jobs, setJobs] = useState<SkillCreationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const completed = useRef(new Set<string>());
  const submitting = useRef(false);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const items = await listSkillCreations();
        if (stopped) return;
        setJobs(items);
        setPollError("");
        for (const job of items) {
          if (!active(job) && !completed.current.has(job.id)) {
            completed.current.add(job.id);
            if (job.results.some((r) => r.status === "installed")) refresh();
          }
        }
      } catch (e) {
        if (!stopped) setPollError(String(e instanceof Error ? e.message : e));
      } finally {
        if (!stopped) { setLoading(false); timer = setTimeout(poll, 3000); }
      }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [refresh]);

  async function submit(input: SkillCreationInput) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const job = await createSkills(input);
      setJobs((previous) => [job, ...previous.filter((j) => j.id !== job.id)]);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { submitting.current = false; setBusy(false); }
  }
  const modes = [
    { id: "site" as const, icon: Globe2, title: zh ? "从站点" : "Website", description: zh ? "获取来源数据" : "Access source data" },
    { id: "task" as const, icon: Route, title: zh ? "从任务" : "Task", description: zh ? "提炼可复用方法" : "Build reusable methods" },
    { id: "trace" as const, icon: ListTree, title: zh ? "从轨迹" : "Trace", description: zh ? "补齐失败能力" : "Learn from failures" },
  ];
  const inputClass = "w-full rounded-xl border border-line bg-paper/40 px-4 py-3 text-[14px] leading-6 text-ink outline-none transition focus:border-accent/50 focus:bg-surface focus:ring-3 focus:ring-accent/5 placeholder:text-ink-faint";
  return <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_320px] xl:gap-14">
    <section className="min-w-0 rounded-[24px] border border-line bg-surface p-5 shadow-[0_8px_40px_-20px_rgba(21,34,56,0.12)] sm:p-8" aria-label={zh ? "新建技能" : "New skill"}>
      <fieldset className="mb-7">
        <legend className="mb-4 text-[13px] font-medium text-ink">{zh ? "从什么开始？" : "Where would you like to start?"}</legend>
        <div className="grid grid-cols-3 gap-2 sm:gap-3">{modes.map(({ id, icon: Icon, title, description }) => <label key={id} className={`relative cursor-pointer rounded-xl border p-3 transition sm:p-4 ${kind === id ? "border-accent/50 bg-accent/5" : "border-line hover:border-line-strong hover:bg-paper"}`}>
          <input type="radio" name="skill-source" value={id} checked={kind === id} onChange={() => setKind(id)} className="peer sr-only" />
          <span className="pointer-events-none absolute inset-0 rounded-xl peer-focus-visible:ring-2 peer-focus-visible:ring-accent" />
          <Icon size={19} className={`mb-3 ${kind === id ? "text-accent-ink" : "text-ink-faint"}`} />
          {kind === id && <Check size={12} className="absolute right-3 top-3 text-accent-ink" />}
          <span className={`block text-[13px] font-medium ${kind === id ? "text-accent-ink" : "text-ink"}`}>{title}</span>
          <span className="mt-1 hidden text-[10px] text-ink-dim sm:block">{description}</span>
        </label>)}</div>
      </fieldset>
      <form className="space-y-6" onSubmit={(e) => {
        e.preventDefault();
        void submit({ kind, site: kind === "site" ? site : undefined, text,
          categories: kind === "site" ? ["access"] : categories, max_requests: kind === "site" ? 1 : max });
      }}>
        {kind === "site" && <label className="block">
          <span className="mb-2.5 block text-[13px] font-medium text-ink">{zh ? "站点地址" : "Website URL"}</span>
          <input className={`${inputClass} font-mono text-[13px]`} required maxLength={2048} placeholder="https://github.com" value={site} onChange={(e) => setSite(e.target.value)} />
        </label>}
        <label className="block">
          <span className="mb-2.5 flex items-center gap-2 text-[13px] font-medium text-ink">{kind === "site" ? (zh ? "希望它学会什么？" : "What should it learn?") : kind === "trace" ? (zh ? "发生了什么问题？" : "What went wrong?") : (zh ? "你想完成什么任务？" : "What would you like to accomplish?")}{kind === "site" && <span className="text-[11px] font-normal text-ink-faint">{zh ? "选填" : "Optional"}</span>}</span>
          <textarea className={`${inputClass} min-h-36 resize-y`} rows={kind === "site" ? 5 : 7} maxLength={64000} required={kind !== "site"} value={text} onChange={(e) => setText(e.target.value)} placeholder={kind === "site" ? (zh ? "例如：搜索仓库、读取 Issue 和讨论，并保留原始链接。" : "For example: search repositories, read issues and discussions, and preserve source links.") : kind === "task" ? (zh ? "描述具体目标，以及你希望得到的结果。" : "Describe your goal and the result you need.") : (zh ? "粘贴失败的执行记录，补充当时的目标与上下文。" : "Paste the failed run, its objective, and relevant context.")} />
        </label>
        {kind !== "site" && <details className="group border-t border-line pt-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-[12px] text-ink-dim [&::-webkit-details-marker]:hidden"><SlidersHorizontal size={14} />{zh ? "生成选项" : "Generation options"}<ChevronDown size={13} className="ml-auto transition-transform group-open:rotate-180" /></summary>
          <div className="space-y-4 pt-4"><fieldset className="flex flex-wrap gap-2"><legend className="mb-2 text-[11px] text-ink-faint">{zh ? "允许生成的类别" : "Allowed categories"}</legend>
            {["access", "strategy", "orchestrator"].map((category) => <label key={category} className="flex cursor-pointer items-center gap-2 rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim"><input className="accent-accent" type="checkbox" checked={categories.includes(category)} onChange={(e) => setCategories((old) => e.target.checked ? [...old, category] : old.filter((c) => c !== category))} />{category}</label>)}
          </fieldset><label className="flex items-center justify-between text-[12px] text-ink-dim">{zh ? "最多生成技能数" : "Maximum skills"}<input type="number" min={1} max={10} required value={max} onChange={(e) => setMax(e.target.valueAsNumber)} className="w-16 rounded-lg border border-line bg-paper px-2 py-1.5 text-center outline-none focus:border-accent" /></label></div>
        </details>}
        {error && <p role="alert" className="rounded-xl bg-err/5 p-3 text-[12px] text-err">{error}</p>}
        <div className="border-t border-line pt-5">
          <button type="submit" disabled={disabled || busy || (kind !== "site" && categories.length === 0)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-5 py-3.5 text-[14px] font-medium text-white shadow-[0_4px_12px_-4px_rgba(37,99,235,0.4)] transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40">{busy ? <Loader2 size={16} className="animate-spin" /> : null}{busy ? (zh ? "正在提交…" : "Submitting…") : (zh ? "创建技能" : "Create skill")}{!busy && <ArrowRight size={16} />}</button>
          <p className="mt-3 text-center text-[11px] leading-5 text-ink-faint">{zh ? "自动分析需求，验证通过后保存至技能库。" : "Requirements are analyzed automatically. Validated skills are saved to your library."}</p>
        </div>
      </form>
    </section>
    <SkillCreationHistory jobs={jobs} zh={zh} loading={loading} error={pollError} disabled={disabled || busy} onRetry={(input) => void submit(input)} />
  </div>;
}
