"use client";
import { useRef, useState } from "react";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";
import { assistant, type Plan, type PlanInput } from "@/lib/assistant";
import type { SourceSelection } from "@/lib/types";
import MaterialPicker from "./MaterialPicker";
import MobileSheet from "./MobileSheet";
import s from "./mobile-assistant.module.css";
export default function PlanEditor({ plan, library, onClose, onSave, onUpload }: { plan?: Plan; library: LocalLibraryController; onClose: () => void; onSave: () => void; onUpload: () => void }) {
  const [form, setForm] = useState<PlanInput>(() => plan ? { title: plan.title, instruction: plan.instruction, frequency: plan.frequency, time: plan.time, weekday: plan.weekday, date: plan.date, timezone: plan.timezone, effort: plan.effort, max_time: plan.max_time, sources: plan.sources, active: plan.active, version: plan.version } : { title: "每日 AI 简报", instruction: "整理过去一天值得关注的 AI 新闻，说明发生了什么、为什么值得关注，并附上原始来源。", frequency: "daily", time: "08:00", weekday: 1, date: null, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai", effort: "medium", max_time: 300, sources: { mode: "web" }, active: false });
  const [error, setError] = useState(""); const [saving, setSaving] = useState(false); const [picking, setPicking] = useState<"local" | "hybrid" | null>(null);
  const key = useRef(crypto.randomUUID());
  const set = <K extends keyof PlanInput>(field: K, value: PlanInput[K]) => { key.current = crypto.randomUUID(); setForm(old => ({ ...old, [field]: value })); };
  const save = async () => { if (saving) return; setSaving(true); setError(""); try { await assistant(plan ? `/schedules/${plan.id}` : "/schedules", plan ? "PUT" : "POST", form, key.current); onSave(); onClose(); } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); } finally { setSaving(false); } };
  if (picking) return <MaterialPicker controller={library} mode={picking} initialSelection={form.sources} onClose={() => setPicking(null)} onUpload={onUpload} onApply={(sources: SourceSelection) => { set("sources", sources); setPicking(null); }} />;
  return <MobileSheet title={plan ? "编辑定时计划" : "安排定时简报"} subtitle="保存到 SearchOS，手机离开后也会按时执行。" onClose={onClose} footer={<button className={s.primaryButton} disabled={saving || !form.title.trim() || !form.instruction.trim()} onClick={() => void save()}>{saving ? "正在保存…" : form.active ? "保存并启用" : "保存为暂停"}</button>}>
    <label className={s.fieldLabel}>计划名称<input value={form.title} maxLength={120} onChange={e => set("title", e.target.value)} /></label>
    <label className={s.fieldLabel}>让助理做什么<textarea rows={5} maxLength={12000} value={form.instruction} onChange={e => set("instruction", e.target.value)} /></label>
    <div className={s.formGrid}><label className={s.fieldLabel}>重复频率<select value={form.frequency} onChange={e => set("frequency", e.target.value as PlanInput["frequency"])}><option value="daily">每天</option><option value="weekly">每周</option><option value="once">仅一次</option></select></label><label className={s.fieldLabel}>执行时间<input type="time" required value={form.time} onChange={e => set("time", e.target.value)} /></label></div>
    {form.frequency === "weekly" && <label className={s.fieldLabel}>星期<select value={form.weekday} onChange={e => set("weekday", Number(e.target.value))}>{["一","二","三","四","五","六","日"].map((d, i) => <option key={d} value={i+1}>星期{d}</option>)}</select></label>}
    {form.frequency === "once" && <label className={s.fieldLabel}>日期<input type="date" value={form.date || ""} onChange={e => set("date", e.target.value)} /></label>}
    <label className={s.fieldLabel}>时区<input value={form.timezone} placeholder="Asia/Shanghai" onChange={e => set("timezone", e.target.value)} /></label>
    <label className={s.fieldLabel}>资料范围<select value={form.sources.mode} onChange={e => e.target.value === "web" ? set("sources", { mode: "web" }) : setPicking(e.target.value as "local" | "hybrid")}><option value="web">公开网络</option><option value="local">只用我的资料</option><option value="hybrid">网络与资料</option></select></label>
    {form.sources.local && <button className={s.outlineButton} onClick={() => setPicking(form.sources.mode === "local" ? "local" : "hybrid")}>已指定 {form.sources.local.document_ids?.length || 0} 份资料 · 重新选择</button>}
    <div className={s.formGrid}><label className={s.fieldLabel}>研究深度<select disabled={form.sources.mode === "local"} value={form.effort} onChange={e => set("effort", e.target.value as PlanInput["effort"])}><option value="low">快速</option><option value="medium">标准</option><option value="high">深入</option><option value="max">全面</option></select></label><label className={s.fieldLabel}>最长执行（秒）<input type="number" min={30} max={3600} value={form.max_time} onChange={e => set("max_time", Number(e.target.value))} /></label></div>
    {form.sources.mode === "local" && <p className={s.caption}>纯资料任务使用专门的文档研究策略，联网研究深度不适用。执行时间上限仍然生效。</p>}
    <label className={s.toggleRow}><span><b>启用自动执行</b><small>按计划调用当前配置的模型，产生相应用量。</small></span><input type="checkbox" checked={form.active} onChange={e => set("active", e.target.checked)} /></label>
    <p className={s.caption}>SearchOS 服务需要保持运行。错过一小时以内的任务会补跑一次，更早的任务会跳过。</p>
    {error && <p role="alert" className={s.error}>{error}</p>}
  </MobileSheet>;
}
