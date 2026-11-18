"use client";

import { useId, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Check, ChevronRight, Plus, RotateCcw, Search } from "lucide-react";
import { putMiddleware } from "@/lib/api";
import { assemblyOrderError } from "@/lib/middleware-assembly";
import type { MiddlewareComponent } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import { OfflineSkeleton, SectionShell } from "@/components/settings/primitives";
import Toggle from "@/components/settings/controls/Toggle";
import MiddlewareCallChain from "./MiddlewareCallChain";

const CATEGORIES = {
  context: { zh: "上下文", en: "Context" },
  extraction: { zh: "证据抽取", en: "Extraction" },
  sensor: { zh: "运行检测", en: "Sensors" },
};

export default function MiddlewareSection() {
  const { settings, status, mutate, notify, uiPrefs } = useSettings();
  const language = uiPrefs.language;
  const zh = language === "zh";
  const [active, setActive] = useState("orchestrator");
  const [drafts, setDrafts] = useState<Record<string, string[]>>({});
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [mode, setMode] = useState<"assemble" | "chain">("assemble");
  const detailPrefix = useId();
  const savingRef = useRef(false);
  const view = settings?.middleware;
  const title = zh ? "Middleware 装配" : "Middleware assembly";
  const description = zh
    ? "按用途选择组件与顺序；调用链解释它们如何包住模型与工具。"
    : "Choose components and order by purpose; the call chain shows how they wrap the model and tools.";

  if (!view) return (
    <SectionShell id="middleware" title={title} description={description}>
      {!settings ? <OfflineSkeleton /> : <p className="text-[13px] text-ink-dim">
        {zh ? "当前后端尚未提供装配配置，请重启 API 后重试。" : "Restart the API to load middleware configuration."}
      </p>}
    </SectionShell>
  );

  const pipeline = view.pipelines.find((item) => item.id === active) ?? view.pipelines[0];
  if (!pipeline) return null;
  const selected = drafts[pipeline.id] ?? pipeline.selected;
  const dirty = JSON.stringify(selected) !== JSON.stringify(pipeline.selected);
  const disabled = saving || status !== "ready";
  const invalidOrder = assemblyOrderError(selected);
  const catalog = new Map(view.catalog.map((item) => [item.id, item]));
  const pool = pipeline.available.filter((id) => !selected.includes(id)).filter((id) => {
    const item = catalog.get(id);
    if (!item) return false;
    const haystack = `${id} ${item.label[language]} ${item.description[language]}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });
  const mounted = selected.map((id) => catalog.get(id)).filter((item): item is MiddlewareComponent => !!item);
  const change = (next: string[]) => setDrafts((current) => ({ ...current, [pipeline.id]: next }));
  const toggle = (id: string) => change(selected.includes(id) ? selected.filter((name) => name !== id) : [...selected, id]);
  const move = (id: string, direction: number) => {
    const index = selected.indexOf(id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= selected.length) return;
    const next = [...selected];
    [next[index], next[target]] = [next[target], next[index]];
    change(next);
  };
  const save = async (reset = false) => {
    if (savingRef.current || (!reset && invalidOrder)) return;
    savingRef.current = true;
    setSaving(true);
    try {
      const result = await mutate({
        call: () => putMiddleware(pipeline.id, reset ? null : selected),
        merge: (current, middleware) => ({ ...current, middleware }),
        errorLabel: zh ? "装配保存失败" : "Couldn't save middleware",
      });
      if (result) {
        setDrafts((current) => {
          const next = { ...current };
          delete next[pipeline.id];
          return next;
        });
        notify(zh ? "装配已保存，将用于后续创建的 agent。" : "Saved for subsequently created agents.", "success");
      }
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <SectionShell id="middleware" title={title} description={description}>
      <div className="flex flex-wrap gap-1.5" aria-label={zh ? "Agent 用途" : "Agent purpose"}>
        {view.pipelines.map((item) => (
          <button key={item.id} type="button" aria-pressed={pipeline.id === item.id} disabled={saving}
            onClick={() => setActive(item.id)}
            className={`rounded-lg border px-3 py-2 text-[12px] transition-colors disabled:opacity-50 ${pipeline.id === item.id ? "border-accent/40 bg-clay/60 text-accent-ink" : "border-line text-ink-dim hover:bg-surface-2"}`}>
            {item.label[language]}{drafts[item.id] && JSON.stringify(drafts[item.id]) !== JSON.stringify(item.selected) ? " ·" : ""}
          </button>
        ))}
      </div>

      <div className="flex rounded-lg border border-line p-0.5 w-fit" aria-label={zh ? "装配视图" : "Assembly view"}>
        {(["assemble", "chain"] as const).map((id) => (
          <button key={id} type="button" aria-pressed={mode === id} onClick={() => setMode(id)}
            className={`rounded-md px-2.5 py-1.5 text-[11px] ${mode === id ? "bg-clay text-accent-ink" : "text-ink-dim hover:bg-surface-2"}`}>
            {id === "assemble" ? (zh ? "装配" : "Assemble") : (zh ? "调用链" : "Call chain")}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12px] text-ink-dim">
        <span className="text-[13px] font-medium text-ink">
          {pipeline.label[language]}
          <span className="ml-2 text-[12px] font-normal text-ink-dim">{selected.length} / {pipeline.available.length} {zh ? "已装载" : "mounted"}</span>
        </span>
        <span className="text-[11px] text-ink-faint">
          {zh ? "外层 → 内层 · 后续新建 agent 生效" : "Outer → inner · applies to agents created next"}
          {dirty ? (zh ? " · 未保存" : " · Unsaved") : ""}
        </span>
      </div>

      {mode === "chain" ? (
        <MiddlewareCallChain items={mounted} language={language} />
      ) : (
        <>
          <p className="text-[11px] leading-relaxed text-ink-faint">
            {zh
              ? "编号是 wrapper 从外到内的顺序。条件芯片表示运行时才决定是否挂载。"
              : "Numbers are wrapper order from outer to inner. A condition chip means the component mounts only when that runtime requirement is met."}
          </p>
          {selected.length === 0 && <p className="rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim">
            {zh ? "当前为空组合：不装载业务 middleware，基础运行设施仍保留。" : "Empty composition: no business middleware; core runtime facilities remain."}
          </p>}
          <div className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface" aria-label={zh ? "已装载栈" : "Mounted stack"}>
            {selected.map((id) => {
              const item = catalog.get(id);
              if (!item) return null;
              const index = selected.indexOf(id);
              const detailKey = `${pipeline.id}:${id}`;
              const open = expanded === detailKey;
              const detailsId = `${detailPrefix}-${pipeline.id}-${id}`;
              return (
                <div key={id}>
                  <div className="flex min-h-11 items-center gap-2 px-3">
                    <span className="w-5 shrink-0 text-center font-mono text-[11px] tabular-nums text-accent-ink">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <button type="button" aria-expanded={open} aria-controls={detailsId}
                      onClick={() => setExpanded(open ? null : detailKey)}
                      className="flex min-w-0 flex-1 items-center gap-1.5 self-stretch py-2 text-left text-[13px] text-ink hover:text-accent-ink">
                      <ChevronRight size={13} aria-hidden="true" className={`shrink-0 text-ink-faint transition-transform ${open ? "rotate-90" : ""}`} />
                      <span className="min-w-0">
                        <span className="block break-words">{item.label[language]}</span>
                        {item.condition && <span className="mt-0.5 inline-block rounded-full border border-line bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">{item.condition[language]}</span>}
                      </span>
                    </button>
                    <div className="flex shrink-0 gap-0.5">
                      {[-1, 1].map((direction) => {
                        const label = `${direction < 0 ? (zh ? "上移" : "Move up") : (zh ? "下移" : "Move down")} ${item.label[language]}`;
                        return <button key={direction} type="button" onClick={() => move(id, direction)} title={label} aria-label={label}
                          disabled={disabled || index + direction < 0 || index + direction >= selected.length}
                          className="rounded p-1.5 text-ink-dim hover:bg-surface-2 disabled:opacity-25">
                          {direction < 0 ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
                        </button>;
                      })}
                    </div>
                    <Toggle checked disabled={disabled} onChange={() => toggle(id)}
                      label={`${zh ? "挂载" : "Mount"} ${item.label[language]}`} />
                  </div>
                  <div id={detailsId} hidden={!open} className="space-y-2 border-t border-line bg-surface-2/40 px-3 py-3 sm:pl-10">
                    {open && <>
                      <div className="flex flex-wrap items-center gap-2">
                        <code className="break-all text-[11px] text-ink-dim">{id}</code>
                        <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">{CATEGORIES[item.category][language]}</span>
                      </div>
                      <p className="text-[12px] leading-relaxed text-ink-dim">{item.description[language]}</p>
                      <div className="flex flex-wrap gap-1">{item.hooks.map((hook) => <span key={hook} className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-dim">{hook}</span>)}</div>
                    </>}
                  </div>
                </div>
              );
            })}
          </div>
          <details className="rounded-xl border border-dashed border-line bg-surface-2/40 px-3 py-2.5">
            <summary className="cursor-pointer select-none text-[12px] text-ink-dim">
              {zh ? `添加组件 · ${pool.length} 项未装载` : `Add component · ${pool.length} not mounted`}
            </summary>
            <label className="input-surface mt-2 flex min-w-0 items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-ink-faint">
              <Search size={14} className="shrink-0" />
              <input value={query} onChange={(event) => setQuery(event.target.value)}
                aria-label={zh ? "搜索 Middleware" : "Search middleware"} placeholder={zh ? "搜索组件名称或作用…" : "Find a component…"}
                className="min-w-0 w-full bg-transparent text-[12px] text-ink outline-none" />
            </label>
            <div className="mt-2 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
              {pool.map((id) => {
                const item = catalog.get(id)!;
                return (
                  <div key={id} className="flex min-h-11 items-center gap-2 px-3">
                    <span className="min-w-0 flex-1 py-2 text-[13px] text-ink">
                      <span className="block break-words">{item.label[language]}</span>
                      {item.condition && <span className="mt-0.5 inline-block rounded-full border border-line bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">{item.condition[language]}</span>}
                    </span>
                    <button type="button" disabled={disabled} onClick={() => toggle(id)}
                      className="flex items-center gap-1 rounded-md px-2 py-1.5 text-[11px] text-accent-ink hover:bg-clay disabled:opacity-40">
                      <Plus size={12} />{zh ? "添加" : "Add"}
                    </button>
                    <Toggle checked={false} disabled={disabled} onChange={() => toggle(id)}
                      label={`${zh ? "挂载" : "Mount"} ${item.label[language]}`} />
                  </div>
                );
              })}
              {pool.length === 0 && <p className="py-4 text-center text-[12px] text-ink-faint">{zh ? "没有可添加的组件。" : "No components to add."}</p>}
            </div>
          </details>
        </>
      )}

      {invalidOrder && <p role="alert" className="rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[12px] text-warn">
        {zh ? "请将「预算控制」放在「上下文压缩」之前，以便在压缩历史前记录用量。" : "Place Budget control before Context compaction to record usage before compacting history."}
      </p>}
      <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface p-3 shadow-sm">
        <button type="button" disabled={disabled || (!pipeline.customized && !dirty)} onClick={() => save(true)}
          className="flex items-center gap-1.5 rounded-lg px-2 py-2 text-[12px] text-ink-dim hover:bg-surface-2 disabled:opacity-40">
          <RotateCcw size={13} /> {zh ? "恢复默认" : "Restore defaults"}
        </button>
        <div className="flex items-center gap-2">
          {dirty && <button type="button" disabled={disabled} onClick={() => change([...pipeline.selected])}
            className="rounded-lg px-2 py-2 text-[12px] text-ink-dim hover:bg-surface-2 disabled:opacity-40">{zh ? "撤销修改" : "Discard"}</button>}
          <button type="button" disabled={disabled || !dirty || invalidOrder} onClick={() => save()}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[12px] text-white hover:opacity-90 disabled:opacity-40">
            <Check size={14} /> {saving ? (zh ? "保存中…" : "Saving…") : (zh ? "保存装配" : "Save assembly")}
          </button>
        </div>
      </div>
    </SectionShell>
  );
}
