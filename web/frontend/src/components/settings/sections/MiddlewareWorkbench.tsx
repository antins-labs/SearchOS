"use client";

import { useRef, useState, type PointerEvent } from "react";
import { ArrowDown, ArrowUp, GripVertical, Plus, X } from "lucide-react";
import type { MiddlewareComponent } from "@/lib/types";
import { insertMiddleware } from "@/lib/middleware-assembly";
import MiddlewareCallChain from "./MiddlewareCallChain";

interface Props {
  catalog: MiddlewareComponent[];
  available: string[];
  selected: string[];
  visible: string[];
  language: "zh" | "en";
  disabled: boolean;
  onChange: (selected: string[]) => void;
}
type DropTarget = { zone: "assembly"; slot: number } | { zone: "library" };
type Drag = { id: string; x: number; y: number; target: DropTarget | null };
const TINTS = {
  context: "border-l-blue-400",
  extraction: "border-l-emerald-400",
  sensor: "border-l-amber-400",
};

export default function MiddlewareWorkbench({ catalog, available, selected, visible, language, disabled, onChange }: Props) {
  const zh = language === "zh";
  const board = useRef<HTMLDivElement>(null);
  const origin = useRef<{ id: string; x: number; y: number; moved: boolean } | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [inspected, setInspected] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const byId = new Map(catalog.map((item) => [item.id, item]));
  const items = selected.map((id) => byId.get(id)).filter((item): item is MiddlewareComponent => !!item);
  const library = available.filter((id) => !selected.includes(id) && visible.includes(id));
  const detail = inspected ? byId.get(inspected) : null;

  const update = (next: string[], id: string) => {
    if (disabled) return;
    onChange(next);
    const index = next.indexOf(id);
    const name = byId.get(id)?.label[language] ?? id;
    setAnnouncement(index < 0 ? (zh ? `已移除 ${name}` : `Removed ${name}`)
      : (zh ? `${name} 已放置在第 ${index + 1} 位` : `${name} placed at position ${index + 1}`));
  };
  const move = (id: string, direction: number) => {
    const index = selected.indexOf(id);
    if (index < 0 || index + direction < 0 || index + direction >= selected.length) return;
    update(insertMiddleware(selected, id, index + (direction > 0 ? 2 : -1)), id);
  };
  const targetAt = (x: number, y: number): DropTarget | null => {
    const element = document.elementFromPoint(x, y);
    const zone = element?.closest<HTMLElement>("[data-drop-zone]");
    if (!zone || !board.current?.contains(zone)) return null;
    if (zone.dataset.dropZone === "library") return { zone: "library" };
    const row = element?.closest<HTMLElement>("[data-assembly-index]");
    if (!row) return { zone: "assembly", slot: selected.length };
    const rect = row.getBoundingClientRect();
    return { zone: "assembly", slot: Number(row.dataset.assemblyIndex) + (y > rect.top + rect.height / 2 ? 1 : 0) };
  };
  const cancel = () => { origin.current = null; setDrag(null); };
  const start = (event: PointerEvent<HTMLButtonElement>, id: string) => {
    if (disabled || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    origin.current = { id, x: event.clientX, y: event.clientY, moved: false };
  };
  const track = (event: PointerEvent<HTMLButtonElement>) => {
    const source = origin.current;
    if (!source || disabled) return;
    if (Math.hypot(event.clientX - source.x, event.clientY - source.y) < 5 && !source.moved) return;
    source.moved = true;
    const element = document.elementFromPoint(event.clientX, event.clientY);
    const zone = element?.closest<HTMLElement>("[data-drop-zone]");
    if (zone && board.current?.contains(zone)) {
      const rect = zone.getBoundingClientRect();
      if (event.clientY < rect.top + 28) zone.scrollTop -= 12;
      else if (event.clientY > rect.bottom - 28) zone.scrollTop += 12;
    }
    setDrag({ id: source.id, x: event.clientX, y: event.clientY, target: targetAt(event.clientX, event.clientY) });
  };
  const finish = (event: PointerEvent<HTMLButtonElement>) => {
    const source = origin.current;
    const target = targetAt(event.clientX, event.clientY);
    if (source?.moved && target && !disabled) {
      if (target.zone === "assembly") update(insertMiddleware(selected, source.id, target.slot), source.id);
      else if (selected.includes(source.id)) update(selected.filter((id) => id !== source.id), source.id);
    }
    cancel();
  };
  const handle = (id: string) => <button type="button" disabled={disabled}
    aria-label={`${zh ? "拖动" : "Drag"} ${byId.get(id)!.label[language]}`}
    title={zh ? "拖动装配；也可用方向键排序，Esc 取消" : "Drag to assemble; arrow keys reorder, Esc cancels"}
    onPointerDown={(event) => start(event, id)} onPointerMove={track} onPointerUp={finish} onPointerCancel={cancel} onLostPointerCapture={cancel}
    onKeyDown={(event) => {
      if (event.key === "Escape") { event.preventDefault(); cancel(); }
      if (selected.includes(id) && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        event.preventDefault(); move(id, event.key === "ArrowUp" ? -1 : 1);
      }
    }}
    className="touch-none select-none rounded p-1.5 text-ink-faint hover:bg-surface-2 active:cursor-grabbing disabled:opacity-30 cursor-grab">
    <GripVertical size={14} />
  </button>;
  const slot = (index: number) => <div aria-hidden="true" className={`h-1 rounded-full transition-colors ${drag?.target?.zone === "assembly" && drag.target.slot === index ? "bg-accent" : "bg-transparent"}`} />;

  return <div className="@container space-y-3">
    <p className="text-[11px] leading-relaxed text-ink-dim">{zh
      ? "拖动手柄添加或排序，拖回组件库移除；也可使用加号和方向按钮。筛选仅作用于组件库。"
      : "Drag handles to add or reorder; drag back to remove. Buttons and arrow keys also work. Filters apply to the library."}</p>
    <div ref={board} className="grid gap-3 @sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <div className="min-w-0 overflow-hidden rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-3 py-2 text-[12px] font-medium text-ink">{zh ? "组件库" : "Library"} <span className="text-[10px] font-normal text-ink-faint">{library.length}</span></h3>
        <div data-drop-zone="library" className={`h-64 overflow-y-auto overscroll-contain p-2 ${drag?.target?.zone === "library" ? "bg-clay/50 ring-2 ring-inset ring-accent/40" : "bg-surface-2/30"}`}>
          {library.map((id) => {
            const item = byId.get(id)!;
            return <div key={id} className={`mb-2 flex items-center gap-0.5 rounded-lg border border-line border-l-2 bg-surface p-1 ${TINTS[item.category]}`}>
              {handle(id)}
              <button type="button" onClick={() => setInspected(id)} className="min-w-0 flex-1 break-words py-1 text-left text-[11px] text-ink hover:text-accent-ink">{item.label[language]}</button>
              <button type="button" disabled={disabled} onClick={() => update([...selected, id], id)} aria-label={`${zh ? "添加" : "Add"} ${item.label[language]}`}
                className="rounded p-1.5 text-accent-ink hover:bg-clay disabled:opacity-30"><Plus size={13} /></button>
            </div>;
          })}
          {library.length === 0 && <p className="px-2 py-4 text-[11px] leading-relaxed text-ink-faint">{zh ? "没有待添加的匹配组件。可将已装配组件拖回这里移除。" : "No matching components to add. Drop assembled components here to remove them."}</p>}
        </div>
      </div>
      <div className="min-w-0 overflow-hidden rounded-xl border border-line bg-surface">
        <h3 className="flex items-center justify-between border-b border-line px-3 py-2 text-[12px] font-medium text-ink">
          {zh ? "装配顺序" : "Assembly order"}<span className="text-[10px] font-normal text-ink-faint">{zh ? "外层 → 内层" : "Outer → inner"}</span>
        </h3>
        <div data-drop-zone="assembly" aria-label={zh ? "已装配组件" : "Assembled middleware"} className="h-64 overflow-y-auto overscroll-contain bg-surface-2/30 p-2">
          {items.map((item, index) => <div key={item.id} data-assembly-index={index}>
            {slot(index)}
            <div className={`flex items-center gap-0.5 rounded-lg border border-l-2 p-1 ${TINTS[item.category]} ${inspected === item.id ? "border-accent/40 bg-clay/40" : "border-line bg-surface"} ${drag?.id === item.id ? "opacity-40" : ""}`}>
              {handle(item.id)}
              <span className="w-4 shrink-0 font-mono text-[10px] text-ink-faint">{String(index + 1).padStart(2, "0")}</span>
              <button type="button" onClick={() => setInspected(item.id)} className="min-w-0 flex-1 break-words py-1 text-left text-[11px] text-ink hover:text-accent-ink">{item.label[language]}</button>
              <div className="flex shrink-0">
                {[-1, 1].map((direction) => <button key={direction} type="button" disabled={disabled || index + direction < 0 || index + direction >= selected.length}
                  onClick={() => move(item.id, direction)} aria-label={`${direction < 0 ? (zh ? "上移" : "Move up") : (zh ? "下移" : "Move down")} ${item.label[language]}`}
                  className="rounded px-0.5 py-1.5 text-ink-faint hover:bg-surface-2 disabled:opacity-25">{direction < 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}</button>)}
                <button type="button" disabled={disabled} onClick={() => update(selected.filter((id) => id !== item.id), item.id)} aria-label={`${zh ? "移除" : "Remove"} ${item.label[language]}`}
                  className="rounded p-1 text-ink-faint hover:bg-surface-2 disabled:opacity-25"><X size={12} /></button>
              </div>
            </div>
          </div>)}
          {slot(selected.length)}
          <div className={`rounded-lg border border-dashed px-3 py-3 text-center text-[10px] ${drag?.target?.zone === "assembly" && drag.target.slot === selected.length ? "border-accent bg-clay/40 text-accent-ink" : "border-line text-ink-faint"}`}>
            {zh ? "拖入组件" : "Drop a component"}
          </div>
        </div>
      </div>
    </div>
    <div role="status" className="sr-only">{announcement}</div>
    {drag && !disabled && <div className="pointer-events-none fixed z-50 max-w-56 rounded-lg border border-accent bg-surface px-3 py-2 text-[12px] text-accent-ink shadow-lg"
      style={{ left: drag.x + 10, top: drag.y + 10 }}>{byId.get(drag.id)?.label[language]}</div>}
    <MiddlewareCallChain items={items} language={language} inspected={inspected} onInspect={setInspected} />
    {detail && <div className="space-y-2 rounded-xl border border-line bg-surface-2/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[12px] font-medium text-ink">{detail.label[language]}</h3>
        <button type="button" onClick={() => setInspected(null)} aria-label={zh ? "关闭组件详情" : "Close component details"} className="rounded p-1 text-ink-faint hover:bg-surface-2"><X size={13} /></button>
      </div>
      <p className="text-[12px] leading-relaxed text-ink-dim">{detail.description[language]}</p>
      <code className="block break-all text-[10px] text-ink-faint">{detail.id}</code>
      <div className="flex flex-wrap gap-1">{detail.hooks.map((hook) => <span key={hook} className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-dim">{hook}</span>)}</div>
      {detail.condition && <p className="text-[11px] text-ink-faint">{detail.condition[language]}</p>}
    </div>}
  </div>;
}
