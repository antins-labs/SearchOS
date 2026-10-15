"use client";

import { useId, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Check, ChevronRight, Layers, RotateCcw, Search } from "lucide-react";
import { putMiddleware } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { OfflineSkeleton, SectionShell } from "@/components/settings/primitives";
import Toggle from "@/components/settings/controls/Toggle";

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
  const [category, setCategory] = useState("all");
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const detailPrefix = useId();
  const savingRef = useRef(false);
  const view = settings?.middleware;
  const title = zh ? "Middleware 装配" : "Middleware assembly";
  const description = zh
    ? "选择组件并调整顺序，点击名称查看详情。"
    : "Select and order components. Click a name for details.";

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
  const catalog = new Map(view.catalog.map((item) => [item.id, item]));
  const ordered = [...selected, ...pipeline.available.filter((id) => !selected.includes(id))];
  const visible = ordered.filter((id) => {
    const item = catalog.get(id);
    return item && (category === "all" || item.category === category)
      && `${id} ${item.label[language]} ${item.description[language]}`.toLowerCase().includes(query.toLowerCase());
  });
  const conditional = selected.filter((id) => catalog.get(id)?.condition).length;
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
    if (savingRef.current) return;
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

      <div className="rounded-xl border border-line bg-surface-2/50 px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-[13px] font-medium text-ink"><Layers size={15} />
            {pipeline.label[language]}
            <span className="text-[12px] font-normal text-ink-dim">{selected.length} / {pipeline.available.length} {zh ? "已选择" : "selected"}</span>
          </span>
          <span className="text-[11px] text-ink-faint">{dirty ? (zh ? "未保存" : "Unsaved") : pipeline.customized ? (zh ? "自定义组合" : "Custom") : (zh ? "跟随默认" : "Defaults")}</span>
        </div>
        <details className="mt-1.5 text-[11px] leading-relaxed text-ink-dim">
          <summary className="cursor-pointer select-none">{conditional} {zh ? "项按条件挂载 · 装配规则" : "conditional · Assembly rules"}</summary>
          <p className="mt-2">{zh ? "这是后续 agent 的配置预览；实际挂载取决于任务提供的模型、队列等条件，已创建的 agent 保持原组合。" : "Preview for future agents. Actual mounts depend on task models and queues; existing agents retain their composition."}</p>
          <p className="mt-1">{zh ? "编号表示 wrapper 从外到内的装配顺序；before / after 钩子按各自生命周期执行。新增组件后可用箭头调整位置。" : "Numbers show outer-to-inner wrapper order. Before/after hooks follow their lifecycle. Use arrows to reorder components."}</p>
        </details>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-line px-3 py-2 text-ink-faint">
          <Search size={14} className="shrink-0" />
          <input value={query} onChange={(event) => setQuery(event.target.value)}
            aria-label={zh ? "搜索 Middleware" : "Search middleware"} placeholder={zh ? "搜索组件名称或作用…" : "Find a component…"}
            className="min-w-0 w-full bg-transparent text-[12px] text-ink outline-none" />
        </label>
        <select value={category} onChange={(event) => setCategory(event.target.value)}
          aria-label={zh ? "组件类别" : "Component category"} className="rounded-lg border border-line bg-surface px-2 py-2 text-[12px] text-ink">
          <option value="all">{zh ? "全部类别" : "All categories"}</option>
          {Object.entries(CATEGORIES).map(([id, label]) => <option key={id} value={id}>{label[language]}</option>)}
        </select>
      </div>
      {selected.length === 0 && <p className="rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim">
        {zh ? "当前为空组合：不装载业务 middleware，基础运行设施仍保留。" : "Empty composition: no business middleware; core runtime facilities remain."}
      </p>}

      <div className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {visible.map((id) => {
          const item = catalog.get(id)!;
          const index = selected.indexOf(id);
          const checked = index >= 0;
          const detailKey = `${pipeline.id}:${id}`;
          const open = expanded === detailKey;
          const detailsId = `${detailPrefix}-${pipeline.id}-${id}`;
          return (
            <div key={id}>
              <div className="flex min-h-11 items-center gap-2 px-3">
                <span className={`w-5 shrink-0 text-center font-mono text-[11px] tabular-nums ${checked ? "text-accent-ink" : "text-ink-faint"}`}>
                  {checked ? String(index + 1).padStart(2, "0") : "—"}
                </span>
                <button type="button" aria-expanded={open} aria-controls={detailsId}
                  onClick={() => setExpanded(open ? null : detailKey)}
                  className="flex min-w-0 flex-1 items-center gap-1.5 self-stretch py-2 text-left text-[13px] text-ink hover:text-accent-ink">
                  <ChevronRight size={13} aria-hidden="true" className={`shrink-0 text-ink-faint transition-transform ${open ? "rotate-90" : ""}`} />
                  <span className="min-w-0 break-words">{item.label[language]}</span>
                </button>
                <div className={`flex shrink-0 gap-0.5 ${checked ? "" : "invisible"}`}>
                  {[-1, 1].map((direction) => {
                    const label = `${direction < 0 ? (zh ? "上移" : "Move up") : (zh ? "下移" : "Move down")} ${item.label[language]}`;
                    return <button key={direction} type="button" onClick={() => move(id, direction)} title={label} aria-label={label}
                      disabled={disabled || !checked || index + direction < 0 || index + direction >= selected.length}
                      className="rounded p-1.5 text-ink-dim hover:bg-surface-2 disabled:opacity-25">
                      {direction < 0 ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
                    </button>;
                  })}
                </div>
                <Toggle checked={checked} disabled={disabled} onChange={() => toggle(id)}
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
                  {item.condition && <p className="text-[11px] leading-relaxed text-ink-dim">{item.condition[language]}</p>}
                </>}
              </div>
            </div>
          );
        })}
        {visible.length === 0 && <p className="py-6 text-center text-[13px] text-ink-faint">{zh ? "没有匹配的组件。" : "No matching components."}</p>}
      </div>

      <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface p-3 shadow-sm">
        <button type="button" disabled={disabled || (!pipeline.customized && !dirty)} onClick={() => save(true)}
          className="flex items-center gap-1.5 rounded-lg px-2 py-2 text-[12px] text-ink-dim hover:bg-surface-2 disabled:opacity-40">
          <RotateCcw size={13} /> {zh ? "恢复默认" : "Restore defaults"}
        </button>
        <div className="flex items-center gap-2">
          {dirty && <button type="button" disabled={disabled} onClick={() => change([...pipeline.selected])}
            className="rounded-lg px-2 py-2 text-[12px] text-ink-dim hover:bg-surface-2 disabled:opacity-40">{zh ? "撤销修改" : "Discard"}</button>}
          <button type="button" disabled={disabled || !dirty} onClick={() => save()}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[12px] text-white hover:opacity-90 disabled:opacity-40">
            <Check size={14} /> {saving ? (zh ? "保存中…" : "Saving…") : (zh ? "保存装配" : "Save assembly")}
          </button>
        </div>
      </div>
    </SectionShell>
  );
}
