"use client";
import { useRef, useState } from "react";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";
import { assistant, type Plan, type PlanInput } from "@/lib/assistant";
import type { SourceSelection } from "@/lib/types";
import Select from "@/components/ui/Select";
import MaterialPicker from "./MaterialPicker";
import MobileSheet from "./MobileSheet";
import s from "./mobile-assistant.module.css";
export default function PlanEditor({ plan, library, onClose, onSave, onUpload }: { plan?: Plan; library: LocalLibraryController; onClose: () => void; onSave: () => void; onUpload: () => void }) {
  const [form, setForm] = useState<PlanInput>(() => plan ? { title: plan.title, instruction: plan.instruction, frequency: plan.frequency, time: plan.time, weekday: plan.weekday, date: plan.date, timezone: plan.timezone, effort: plan.effort, max_time: plan.max_time, sources: plan.sources, active: plan.active, version: plan.version } : { title: "每日 AI 简报", instruction: "整理过去一天的 AI 新闻，说明内容与影响，附原始来源。", frequency: "daily", time: "08:00", weekday: 1, date: null, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai", effort: "medium", max_time: 300, sources: { mode: "web" }, active: false });
  const [error, setError] = useState(""); const [saving, setSaving] = useState(false); const [picking, setPicking] = useState<"local" | "hybrid" | null>(null);
  const key = useRef(crypto.randomUUID());
  const set = <K extends keyof PlanInput>(field: K, value: PlanInput[K]) => { key.current = crypto.randomUUID(); setForm(old => ({ ...old, [field]: value })); };
  const save = async () => { if (saving) return; setSaving(true); setError(""); try { await assistant(plan ? `/schedules/${plan.id}` : "/schedules", plan ? "PUT" : "POST", form, key.current); onSave(); onClose(); } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); } finally { setSaving(false); } };
  if (picking) return <MaterialPicker controller={library} mode={picking} initialSelection={form.sources} onClose={() => setPicking(null)} onUpload={onUpload} onApply={(sources: SourceSelection) => { set("sources", sources); setPicking(null); }} />;
  return <MobileSheet title={plan ? "编辑计划" : "新建计划"} onClose={onClose} footer={<button className={s.primaryButton} disabled={saving || !form.title.trim() || !form.instruction.trim()} onClick={() => void save()}>{saving ? "保存中…" : form.active ? "保存并启用" : "保存（暂停）"}</button>}>
    <label className={s.fieldLabel}>名称<input value={form.title} maxLength={120} onChange={e => set("title", e.target.value)} /></label>
    <label className={s.fieldLabel}>任务内容<textarea rows={5} maxLength={12000} value={form.instruction} onChange={e => set("instruction", e.target.value)} /></label>
    <div className={s.formGrid}><div className={s.fieldLabel}><span>频率</span><Select ariaLabel="频率" size="lg" className="w-full" value={form.frequency} options={[{ value: "daily", label: "每天" }, { value: "weekly", label: "每周" }, { value: "once", label: "单次" }]} onChange={value => { if (value !== form.frequency) set("frequency", value as PlanInput["frequency"]); }} /></div><label className={s.fieldLabel}>时间<input type="time" required value={form.time} onChange={e => set("time", e.target.value)} /></label></div>
    {form.frequency === "weekly" && <div className={s.fieldLabel}><span>星期</span><Select ariaLabel="星期" size="lg" className="w-full" value={String(form.weekday)} options={["一","二","三","四","五","六","日"].map((day, index) => ({ value: String(index + 1), label: `星期${day}` }))} onChange={value => { const weekday = Number(value); if (weekday !== form.weekday) set("weekday", weekday); }} /></div>}
    {form.frequency === "once" && <label className={s.fieldLabel}>日期<input type="date" value={form.date || ""} onChange={e => set("date", e.target.value)} /></label>}
    <label className={s.fieldLabel}>时区<input value={form.timezone} placeholder="Asia/Shanghai" onChange={e => set("timezone", e.target.value)} /></label>
    <div className={s.fieldLabel}><span>搜索范围</span><Select ariaLabel="搜索范围" size="lg" className="w-full" value={form.sources.mode} options={[{ value: "web", label: "公开网络" }, { value: "local", label: "只用我的资料" }, { value: "hybrid", label: "网络与资料" }]} onChange={value => { if (value === form.sources.mode) return; if (value === "web") set("sources", { mode: "web" }); else setPicking(value as "local" | "hybrid"); }} /></div>
    {form.sources.local && <button className={s.outlineButton} onClick={() => setPicking(form.sources.mode === "local" ? "local" : "hybrid")}>已选 {form.sources.local.document_ids?.length || 0} 份 · 重选</button>}
    <div className={s.formGrid}><div className={s.fieldLabel}><span>研究深度</span><Select ariaLabel="研究深度" size="lg" className="w-full" disabled={form.sources.mode === "local"} value={form.effort} options={[{ value: "low", label: "快速" }, { value: "medium", label: "标准" }, { value: "high", label: "深入" }, { value: "max", label: "全面" }]} onChange={value => { if (value !== form.effort) set("effort", value as PlanInput["effort"]); }} /></div><label className={s.fieldLabel}>时限（秒）<input type="number" min={30} max={3600} value={form.max_time} onChange={e => set("max_time", Number(e.target.value))} /></label></div>
    {form.sources.mode === "local" && <p className={s.caption}>资料模式下研究深度固定，时限仍生效。</p>}
    <label className={s.toggleRow}><span><b>自动执行</b><small>执行时会调用当前模型并产生用量。</small></span><input type="checkbox" checked={form.active} onChange={e => set("active", e.target.checked)} /></label>
    <p className={s.caption}>服务需持续运行。延误1小时内补跑一次，超过则跳过。</p>
    {error && <p role="alert" className={s.error}>{error}</p>}
  </MobileSheet>;
}
