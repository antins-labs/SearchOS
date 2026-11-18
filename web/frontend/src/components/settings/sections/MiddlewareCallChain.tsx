"use client";

import { useState } from "react";
import { SkipForward } from "lucide-react";
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
  before: { zh: "进入", en: "Enter" },
  enter: { zh: "进入", en: "Enter" },
  call: { zh: "执行", en: "Execute" },
  return: { zh: "返回", en: "Return" },
  after: { zh: "返回", en: "Return" },
};

interface Props {
  items: MiddlewareComponent[];
  language: "zh" | "en";
}

export default function MiddlewareCallChain({ items, language }: Props) {
  const zh = language === "zh";
  const [kind, setKind] = useState<TraceKind>("model");
  const [conditions, setConditions] = useState<Record<string, boolean>>({
    extraction_model: true, steer_queue: true, model_window: true, workspace: true, final_summary: true,
  });
  const [inspected, setInspected] = useState<string | null>(null);
  const mounted = previewMounts(items, conditions);
  const skipped = items.filter((item) => !mounted.includes(item));
  const relevant = Object.keys(CONDITIONS).filter((key) => items.some((item) => key in (item.requirements ?? {})));
  const steps = buildCallChain(mounted, kind);
  const detail = inspected ? items.find((item) => item.id === inspected) : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1" aria-label={zh ? "调用链类型" : "Call chain type"}>
          {(Object.keys(KINDS) as TraceKind[]).map((id) => (
            <button key={id} type="button" aria-pressed={kind === id} onClick={() => setKind(id)}
              className={`rounded-md px-2.5 py-1.5 text-[11px] ${kind === id ? "bg-clay text-accent-ink" : "text-ink-dim hover:bg-surface-2"}`}>
              {KINDS[id][language]}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-ink-faint">{zh ? "配置演示" : "Configuration preview"}</span>
      </div>
      <p className="text-[11px] leading-relaxed text-ink-faint">
        {zh
          ? "外层在上。向下进入模型或工具，返回时逆序经过同一层。实际任务可能提前结束、重试或循环。"
          : "Outer layers are on top. The call descends into the model or tool, then returns through the same layers in reverse. A real task may exit early, retry, or loop."}
      </p>
      {relevant.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-2 rounded-lg border border-line bg-surface-2/50 px-3 py-2 text-[11px] text-ink-dim" aria-label={zh ? "演示条件" : "Preview conditions"}>
          {relevant.map((key) => (
            <label key={key} className="flex items-center gap-1.5">
              <input type="checkbox" checked={conditions[key]} onChange={(event) => setConditions((value) => ({ ...value, [key]: event.target.checked }))}
                className="accent-accent" />
              {CONDITIONS[key as keyof typeof CONDITIONS][language]}
            </label>
          ))}
        </div>
      )}
      <ChainColumn key={JSON.stringify([kind, items.map((item) => item.id), conditions])}
        steps={steps} skipped={skipped} items={mounted} language={language} inspected={inspected}
        onInspect={setInspected} />
      {detail && (
        <div className="space-y-2 rounded-xl border border-line bg-surface-2/40 p-3">
          <h3 className="text-[12px] font-medium text-ink">{detail.label[language]}</h3>
          <p className="text-[12px] leading-relaxed text-ink-dim">{detail.description[language]}</p>
          <code className="block break-all text-[10px] text-ink-faint">{detail.id}</code>
          <div className="flex flex-wrap gap-1">{detail.hooks.map((hook) => <span key={hook} className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-dim">{hook}</span>)}</div>
          {detail.condition && <p className="text-[11px] text-ink-faint">{detail.condition[language]}</p>}
        </div>
      )}
    </div>
  );
}

function ChainColumn({
  steps, skipped, items, language, inspected, onInspect,
}: {
  steps: CallStep[];
  skipped: MiddlewareComponent[];
  items: MiddlewareComponent[];
  language: "zh" | "en";
  inspected: string | null;
  onInspect: (id: string) => void;
}) {
  const zh = language === "zh";
  const [cursor, setCursor] = useState(-1);
  const catalog = new Map(items.map((item) => [item.id, item]));
  const targetLabel = (step: CallStep) => step.hook === "agent_loop"
    ? (zh ? "模型与工具循环" : "Model and tool loop")
    : step.hook === "model" ? (zh ? "调用模型" : "Invoke model") : (zh ? "执行工具" : "Execute tool");
  const label = (step: CallStep) => step.id ? catalog.get(step.id)!.label[language] : targetLabel(step);
  const orderOf = new Map<string, number>();
  items.forEach((item, index) => orderOf.set(item.id, index + 1));

  return (
    <div className="space-y-2" aria-label={zh ? "调用链纵剖面" : "Call chain profile"}>
      <div className="flex items-center justify-between gap-2">
        <button type="button" onClick={() => setCursor(cursor >= steps.length - 1 ? 0 : cursor + 1)}
          className="flex items-center gap-1 rounded-md px-2 py-1.5 text-[11px] text-ink-dim hover:bg-surface-2">
          <SkipForward size={12} />{zh ? "逐步" : "Step"}
        </button>
        <span className="text-[10px] tabular-nums text-ink-faint">{Math.max(cursor + 1, 0)} / {steps.length}</span>
      </div>
      <div className="space-y-1.5">
        {steps.map((step, index) => {
          const isCore = step.phase === "call";
          const isActive = cursor === index;
          const isInspected = !!step.id && inspected === step.id;
          const order = step.id ? orderOf.get(step.id) : undefined;
          return (
            <button key={index} type="button" data-step={index} aria-current={isActive ? "step" : undefined}
              aria-label={`${index + 1}. ${label(step)} · ${PHASES[step.phase][language]}`}
              onClick={() => { setCursor(index); if (step.id) onInspect(step.id); }}
              className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left ${isCore
                ? "justify-center border-accent/40 bg-clay text-accent-ink"
                : isActive ? "border-accent bg-clay/60 text-accent-ink"
                : isInspected ? "border-accent/40 bg-clay/30 text-ink"
                : "border-line bg-surface text-ink"}`}>
              {!isCore && <span className="w-5 shrink-0 text-center font-mono text-[10px] text-ink-faint">{order ? String(order).padStart(2, "0") : "—"}</span>}
              <span className="min-w-0 flex-1">
                <span className={`block break-words text-[12px] ${isCore ? "text-center font-medium" : ""}`}>{label(step)}</span>
                {!isCore && step.hook && <span className="block break-all font-mono text-[9px] text-ink-faint">{step.hook}</span>}
              </span>
              {!isCore && <span className="shrink-0 text-[10px] text-ink-faint">{PHASES[step.phase][language]}</span>}
            </button>
          );
        })}
        {skipped.map((item) => (
          <div key={item.id} className="flex items-center gap-2 rounded-lg border border-dashed border-line px-2.5 py-2 text-[12px] text-ink-faint">
            <span className="w-5 shrink-0 text-center font-mono text-[10px]">—</span>
            <span className="min-w-0 flex-1 break-words">{item.label[language]}{item.condition ? ` · ${item.condition[language]}` : ""}</span>
            <span className="shrink-0 text-[10px]">{zh ? "跳过" : "Skipped"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
