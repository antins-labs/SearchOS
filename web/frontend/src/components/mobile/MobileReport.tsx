"use client";

import { useState } from "react";
import { ArrowRight, BookOpen, ChevronLeft, Copy, Download, RefreshCw } from "lucide-react";
import type { SearchState, WSEvent } from "@/lib/types";
import { declaredCoverageTables } from "@/lib/coverageTables";
import { mobileReportExcerpt } from "@/lib/mobileReportPreview";
import { localCitationLabels } from "@/lib/localCitations";
import Answer, { cleanAnswer } from "@/components/conversation/Answer";
import { useSettings } from "@/components/settings/SettingsProvider";
import MobileReportCards from "./MobileReportCards";
import MobileSheet from "./MobileSheet";
import s from "./mobile-assistant.module.css";

/** Live turns and immutable scheduled reports use the same reading hierarchy. */
export default function MobileReport({ query, answer, searchState, events = [], partial = false, inlineReader = false, onSource, onContinue, onRerun, runDisabled = true }: {
  query: string; answer: string; searchState: SearchState | null; events?: WSEvent[];
  partial?: boolean; inlineReader?: boolean; onSource: (source: string) => void;
  onContinue?: () => void; onRerun?: () => void; runDisabled?: boolean;
}) {
  const [reading, setReading] = useState(false);
  const { notify } = useSettings();
  const markdown = cleanAnswer(answer);
  const evidence = searchState?.evidence_graph?.nodes ?? [];
  const tables = declaredCoverageTables(searchState?.coverage_map).filter(table => table.entities.length > 0);
  const count = tables.reduce((sum, table) => sum + table.entities.length, 0);
  const preview = mobileReportExcerpt(markdown, query);
  const save = () => {
    const url = URL.createObjectURL(new Blob([`# ${query}\n\n${markdown}`], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${query.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-").slice(0, 60) || "SearchOS-report"}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const reader = <div className={s.reader}>
    <p className={s.readerKicker}>{partial ? "阶段结果" : "SearchOS · 报告"}</p>
    <h1>{query}</h1>
    <Answer markdown={markdown} localSources={evidence.map(node => node.source).filter(source => source.startsWith("local://"))} localSourceLabels={localCitationLabels(events, evidence)} evidenceSources={Object.fromEntries(evidence.filter(node => !node.status || node.status === "active").map(node => [node.id, node.source_urls?.length ? node.source_urls : node.source]))} onOpenLocalSource={source => { setReading(false); onSource(source); }} />
    <div className={s.cardButtons} role="toolbar" aria-label="报告操作">
      <button onClick={() => void navigator.clipboard.writeText(markdown).then(() => notify("已复制", "success")).catch(() => notify("复制失败，可长按正文复制。"))}><Copy size={16} />复制</button>
      <button onClick={save}><Download size={16} />保存</button>
      {onRerun && <button disabled={runDisabled} onClick={() => { setReading(false); onRerun(); }}><RefreshCw size={16} />重新研究</button>}
    </div>
  </div>;

  if (reading && inlineReader) return <><button className={s.textButton} onClick={() => setReading(false)}><ChevronLeft size={17} />返回摘要</button>{reader}</>;
  return <>
    <div className={s.reportCover}><p><BookOpen size={15} />{partial ? "阶段结果" : "SearchOS · 报告"}</p><h2>{tables.length === 1 ? tables[0].table_label || query : query}</h2><span>{count ? `${count} 个条目` : "研究报告"}{evidence.length > 0 ? ` · ${evidence.length} 条依据` : ""}</span></div>
    {tables.length ? tables.map(table => <MobileReportCards key={table.table_id} table={table} cells={searchState?.coverage_map.cells ?? {}} evidence={evidence} onOpenSource={onSource} />) : <div className={s.proseSummary}><h3>摘要</h3><p>{preview || "打开全文查看报告。"}</p></div>}
    <button className={s.readReport} onClick={() => setReading(true)}>阅读全文<ArrowRight size={17} /></button>
    {reading && <MobileSheet title="报告全文" onClose={() => setReading(false)} reader footer={onContinue && <button className={s.primaryButton} onClick={() => { setReading(false); onContinue(); }}>继续追问<ArrowRight size={17} /></button>}>{reader}</MobileSheet>}
  </>;
}
