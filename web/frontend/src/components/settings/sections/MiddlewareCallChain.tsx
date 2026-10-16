"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Circle, Pause, Play, RotateCcw, SkipForward } from "lucide-react";
import type { MiddlewareComponent } from "@/lib/types";
import { buildCallChain, previewMounts, type CallStep, type TraceKind } from "@/lib/middleware-assembly";

const CONDITIONS = {
  extraction_model: { zh: "抽取模型", en: "Extraction model" },
  steer_queue: { zh: "追问队列", en: "Follow-up queue" },
  model_window: { zh: "已知上下文窗口", en: "Known context window" },
  workspace: { zh: "工作空间", en: "Workspace" },
  final_summary: { zh: "最终回复抽取", en: "Final answer extraction" },
};
const KINDS = {
  model: { zh: "模型调用", en: "Model call" },
  tool: { zh: "工具调用", en: "Tool call" },
  agent: { zh: "Agent 生命周期", en: "Agent lifecycle" },
};
const PHASES = {
  before: { zh: "前置钩子", en: "Before hook" },
  enter: { zh: "进入", en: "Enter" },
  call: { zh: "执行", en: "Execute" },
  return: { zh: "返回", en: "Return" },
  after: { zh: "后置钩子", en: "After hook" },
};

interface Props {
  items: MiddlewareComponent[];
  language: "zh" | "en";
  inspected: string | null;
  onInspect: (id: string) => void;
}

export default function MiddlewareCallChain({ items, language, inspected, onInspect }: Props) {
  const zh = language === "zh";
  const [kind, setKind] = useState<TraceKind>("model");
  const [conditions, setConditions] = useState<Record<string, boolean>>({
    extraction_model: true, steer_queue: true, model_window: true, workspace: true, final_summary: true,
  });
  const mounted = previewMounts(items, conditions);
  const skipped = items.filter((item) => !mounted.includes(item));
  const relevant = Object.keys(CONDITIONS).filter((key) => items.some((item) => key in (item.requirements ?? {})));
  const steps = buildCallChain(mounted, kind);

  return <div className="overflow-hidden rounded-xl border border-line bg-surface">
    <div className="space-y-2 border-b border-line px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[13px] font-medium text-ink">{zh ? "调用链" : "Call chain"}</h3>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-ink-dim">{zh ? "配置演示" : "Configuration preview"}</span>
      </div>
      <div className="flex flex-wrap gap-1" aria-label={zh ? "调用链类型" : "Call chain type"}>
        {(Object.keys(KINDS) as TraceKind[]).map((id) => <button key={id} type="button" aria-pressed={kind === id}
          onClick={() => setKind(id)} className={`rounded-md px-2.5 py-1.5 text-[11px] ${kind === id ? "bg-clay text-accent-ink" : "text-ink-dim hover:bg-surface-2"}`}>
          {KINDS[id][language]}
        </button>)}
      </div>
      <p className="text-[11px] leading-relaxed text-ink-faint">{zh
        ? "展示业务组件在正常执行路径上的顺序；实际任务可能提前结束、重试或循环。"
        : "Business middleware on a normal execution path. Actual tasks may exit early, retry or loop."}</p>
      {relevant.length > 0 && <details className="text-[11px] text-ink-dim">
        <summary className="cursor-pointer">{zh ? "演示条件" : "Preview conditions"} · {mounted.length}/{items.length} {zh ? "项挂载" : "mounted"}</summary>
        <p className="mt-2 text-ink-faint">{zh ? "仅影响演示，不修改任务配置。" : "Affects this preview only, not task settings."}</p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
          {relevant.map((key) => <label key={key} className="flex items-center gap-1.5">
            <input type="checkbox" checked={conditions[key]} onChange={(event) => setConditions((value) => ({ ...value, [key]: event.target.checked }))}
              className="accent-accent" />{CONDITIONS[key as keyof typeof CONDITIONS][language]}
          </label>)}
        </div>
        {skipped.length > 0 && <p className="mt-2">{zh ? "本次演示跳过：" : "Skipped in this preview: "}{skipped.map((item) => item.label[language]).join("、")}</p>}
      </details>}
    </div>
    <ChainPlayer key={JSON.stringify([kind, items.map((item) => item.id), conditions])}
      steps={steps} items={mounted} language={language} inspected={inspected} onInspect={onInspect} />
  </div>;
}

function ChainPlayer({ steps, items, language, inspected, onInspect }: Props & { steps: CallStep[] }) {
  const zh = language === "zh";
  const [cursor, setCursor] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const catalog = new Map(items.map((item) => [item.id, item]));
  const active = steps[cursor];
  const targetLabel = (step: CallStep) => step.hook === "agent_loop"
    ? (zh ? "模型 ⇄ 工具循环" : "Model ⇄ tool loop")
    : step.hook === "model" ? (zh ? "调用模型" : "Invoke model") : (zh ? "执行工具" : "Execute tool");
  const label = (step: CallStep) => step.id ? catalog.get(step.id)!.label[language] : targetLabel(step);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => {
      if (cursor >= steps.length - 1) setPlaying(false);
      else setCursor(cursor + 1);
    }, 750);
    return () => window.clearTimeout(timer);
  }, [playing, cursor, steps.length]);

  useEffect(() => {
    const container = viewport.current;
    const node = container?.querySelector<HTMLElement>(`[data-step="${cursor}"]`);
    if (container && node) {
      const top = node.offsetTop - container.offsetTop;
      if (top < container.scrollTop || top + node.offsetHeight > container.scrollTop + container.clientHeight) {
        container.scrollTop = Math.max(0, top - container.clientHeight / 2 + node.offsetHeight / 2);
      }
    }
  }, [cursor]);

  const node = (step: CallStep, index: number) => {
    const isActive = cursor === index;
    const isInspected = !!step.id && inspected === step.id;
    return <button key={index} type="button" data-step={index} aria-current={isActive ? "step" : undefined}
      aria-label={`${index + 1}. ${label(step)} · ${PHASES[step.phase][language]}`}
      onClick={() => { setPlaying(false); setCursor(index); if (step.id) onInspect(step.id); }}
      className={`relative flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors motion-reduce:transition-none ${isActive
        ? "border-accent bg-clay text-accent-ink ring-1 ring-accent/20"
        : isInspected ? "border-accent/40 bg-clay/30 text-ink" : "border-line bg-surface text-ink-dim"}`}>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? "bg-accent" : cursor > index ? "bg-accent/40" : "bg-line"}`} />
      <span className="min-w-0 flex-1">
        <span className="block break-words text-[11px] font-medium">{label(step)}</span>
        <span className="block break-all font-mono text-[9px] text-ink-faint">{step.hook}</span>
      </span>
      <span className="font-mono text-[9px] tabular-nums text-ink-faint">{String(index + 1).padStart(2, "0")}</span>
    </button>;
  };
  const callIndex = steps.findIndex((step) => step.phase === "call");
  const inbound = steps.slice(0, callIndex);
  const outbound = steps.slice(callIndex + 1).map((step, index) => ({ step, index: callIndex + 1 + index })).reverse();

  return <>
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
      <div className="flex items-center gap-1">
        <button type="button" onClick={() => { if (!playing && (cursor < 0 || cursor === steps.length - 1)) setCursor(0); setPlaying(!playing); }}
          className="flex items-center gap-1 rounded-md bg-accent px-2.5 py-1.5 text-[11px] text-white">
          {playing ? <Pause size={12} /> : <Play size={12} />}{playing ? (zh ? "暂停" : "Pause") : (zh ? "播放" : "Play")}
        </button>
        <button type="button" onClick={() => { setPlaying(false); setCursor(cursor >= steps.length - 1 ? 0 : cursor + 1); }}
          className="flex items-center gap-1 rounded-md px-2 py-1.5 text-[11px] text-ink-dim hover:bg-surface-2"><SkipForward size={12} />{zh ? "单步" : "Step"}</button>
        <button type="button" onClick={() => { setPlaying(false); setCursor(-1); }} title={zh ? "重置演示" : "Reset preview"} aria-label={zh ? "重置演示" : "Reset preview"}
          className="rounded-md p-1.5 text-ink-dim hover:bg-surface-2"><RotateCcw size={12} /></button>
      </div>
      <span className="text-[10px] tabular-nums text-ink-faint">{cursor + 1} / {steps.length}</span>
    </div>
    <div className="bg-surface-2/40" aria-label={zh ? "调用链图" : "Call chain diagram"}>
    <div ref={viewport} className="relative max-h-64 overflow-y-auto overscroll-contain px-3 pt-3">
      <div className="mb-2 grid grid-cols-2 gap-5 text-[10px] text-ink-faint">
        <span className="flex items-center gap-1"><ArrowDown size={11} />{zh ? "进入 · 正序" : "Enter · forward"}</span>
        <span className="flex items-center gap-1"><ArrowUp size={11} />{zh ? "返回 · 逆序" : "Return · reverse"}</span>
      </div>
      <div className="grid grid-cols-2 items-end gap-5">
        <div className="space-y-1.5 border-l border-accent/20 pl-2">
          {inbound.length ? inbound.map(node) : <p className="py-2 text-[10px] text-ink-faint">{zh ? "直接调用" : "Direct call"}</p>}
        </div>
        <div className="space-y-1.5 border-l border-accent/20 pl-2">
          {outbound.length ? outbound.map(({ step, index }) => node(step, index)) : <p className="py-2 text-[10px] text-ink-faint">{zh ? "直接返回" : "Direct return"}</p>}
        </div>
      </div>
    </div>
    <div className="px-3 pb-3">
      <div className="mx-[20%] h-3 border-x border-b border-accent/30" />
      <div className="mx-auto h-2 w-px bg-accent/30" />
      <div className="mx-auto max-w-64">{node(steps[callIndex], callIndex)}</div>
    </div>
    </div>
    <div className="flex min-h-10 items-center gap-2 border-t border-line px-3 py-2 text-[11px] text-ink-dim" role="status" aria-live={playing ? "off" : "polite"}>
      <Circle size={10} className={active ? "fill-accent text-accent" : "text-ink-faint"} />
      {active ? `${PHASES[active.phase][language]} · ${label(active)}` : (zh ? "点击播放，或选择任意节点查看调用步骤。" : "Play or select a node to inspect the call sequence.")}
    </div>
  </>;
}
