"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpRight, BookOpen, ChevronLeft, ChevronRight, Copy, Download, Layers3, RefreshCw } from "lucide-react";
import type { CoverageCell, CoverageMap, EvidenceNode, SearchState, TableSchema, WSEvent } from "@/lib/types";
import { cellKey, rowLabel } from "@/lib/socmRefs";
import { declaredCoverageTables } from "@/lib/coverageTables";
import { evidenceSourcesById, localCitationLabels } from "@/lib/localCitations";
import Answer, { cleanAnswer } from "@/components/conversation/Answer";
import { useSettings } from "@/components/settings/SettingsProvider";
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
    <Answer markdown={markdown} localSources={evidence.map(node => node.source).filter(source => source.startsWith("local://"))} localSourceLabels={localCitationLabels(events, evidence)} evidenceSources={evidenceSourcesById(evidence)} onOpenLocalSource={source => { setReading(false); onSource(source); }} />
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

function MobileReportCards({ table, cells, evidence, onOpenSource }: {
  table: TableSchema; cells: CoverageMap["cells"]; evidence: EvidenceNode[]; onOpenSource: (source: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const header = useRef<HTMLButtonElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  useEffect(() => { detail.current?.parentElement?.scrollTo({ top: 0 }); }, [selectedId]);
  const listId = useId();
  const rows = reportRows(table, cells);
  const visible = expanded ? rows : rows.slice(0, 3);
  const index = rows.findIndex(row => row.id === selectedId);
  const selected = rows[index];
  const label = table.table_label || "研究结果";
  const sourceName = (url: string) => url.startsWith("local://") ? "本地资料" : new URL(url).hostname.replace(/^www\./, "");
  const toggle = () => setExpanded(value => !value);

  return <section className={s.digest} aria-label={label}>
    <button ref={header} className={s.digestHeader} type="button" aria-expanded={expanded} aria-controls={listId} onClick={toggle}>
      <span className={s.digestIcon}><Layers3 size={22} /></span>
      <span className={s.digestHeading}><b>{label}</b><small>{expanded ? "全部条目" : "条目预览"}</small></span>
      <span className={s.digestCount}>{rows.length}</span><ChevronRight size={17} className={expanded ? s.digestChevronOpen : undefined} />
    </button>
    <div id={listId} className={s.digestRows}>
      {visible.map((row, rowIndex) => <button type="button" className={s.digestRow} key={row.id} aria-label={`查看条目 ${rowIndex + 1}：${row.title}`} onClick={() => setSelectedId(row.id)}>
        <span className={s.digestNumber}>{String(rowIndex + 1).padStart(2, "0")}</span>
        <span className={s.digestRowBody}><b>{row.title}</b>{row.summary && <span className={s.digestExcerpt}>{row.summary}</span>}
          <span className={s.digestMeta}>{row.date && <span>{row.date}</span>}{row.sources[0] && <span>{sourceName(row.sources[0])}</span>}{row.needsReview && <em>待核实</em>}</span>
        </span><ChevronRight size={16} className={s.digestRowArrow} />
      </button>)}
    </div>
    {rows.length > 3 && <button className={s.digestMore} type="button" aria-expanded={expanded} aria-controls={listId} onClick={() => { if (expanded) header.current?.scrollIntoView({ block: "nearest" }); toggle(); }}>
      {expanded ? "收起" : `展开 ${rows.length} 条`}{expanded ? <ArrowUp size={15} /> : <ArrowDown size={15} />}
    </button>}
    {selected && <MobileSheet title="详情" subtitle={`${label} · ${index + 1} / ${rows.length}`} onClose={() => setSelectedId(null)} footer={<div className={s.digestPager}>
      <button disabled={index === 0} onClick={() => setSelectedId(rows[index - 1].id)}><ChevronLeft size={17} />上一条</button><span>{index + 1} / {rows.length}</span><button disabled={index === rows.length - 1} onClick={() => setSelectedId(rows[index + 1].id)}>下一条<ChevronRight size={17} /></button>
    </div>}>
      <div ref={detail} className={s.digestDetail} key={selected.id}>
        <span className={s.digestDetailTag}>条目 {String(index + 1).padStart(2, "0")}</span><h3>{selected.title}</h3>
        {selected.fields.filter(field => field.text !== selected.title || field.conflict || field.status !== "filled").map(field => <section key={field.name} className={s.digestField}>
          <h4>{field.name}{field.conflict ? <span>有冲突</span> : field.status === "uncertain" || field.status === "hard_cell" ? <span>待核实</span> : null}</h4>
          {!field.text || field.status === "missing" ? <p className={s.caption}>暂无信息</p> : field.links.length ? <div className={s.digestSources}>{field.links.map(url => url.startsWith("local://") ? <button key={url} onClick={() => { setSelectedId(null); onOpenSource(url); }}>{sourceName(url)}<ArrowUpRight size={16} /></button> : <a key={url} href={url} target="_blank" rel="noopener noreferrer"><span>{sourceName(url)}<small>{url}</small></span><ArrowUpRight size={16} /></a>)}</div> :
            <Answer markdown={field.text} localSources={evidence.map(node => node.source).filter(source => source.startsWith("local://"))} evidenceSources={evidenceSourcesById(evidence)} onOpenLocalSource={source => { setSelectedId(null); onOpenSource(source); }} />}
        </section>)}
      </div>
    </MobileSheet>}
  </section>;
}

/** Extract prose for the phone preview; wide Markdown tables are opened separately. */
export function mobileReportExcerpt(markdown: string, query: string): string {
  const body = markdown.split(/^#{1,6}\s*(信息来源|参考来源|引用来源|参考文献|来源|References|Sources)\s*$/im)[0];
  const lines = body.split("\n").map(line => line.trim()).filter(line =>
    line && line !== "_(empty body)_" && line !== "(empty body)" &&
    !line.startsWith("|") && !/^:?-{3,}/.test(line) &&
    line.replace(/^#{1,6}\s+/, "") !== query &&
    !/^#{1,6}\s*(数据对比表|信息来源|参考来源|引用来源|参考文献|来源|References|Sources)\s*$/i.test(line),
  );
  const plain = lines.join("\n").replace(/^#{1,6}\s+/gm, "").replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/\*\*/g, "");
  return plain.length > 280 ? `${plain.slice(0, 280)}…` : plain;
}
export interface ReportField { name: string; text: string; status: CoverageCell["status"]; conflict: boolean; links: string[] }
export interface ReportRow { id: string; title: string; summary: string; date: string; fields: ReportField[]; sources: string[]; needsReview: boolean }

const TITLE = /^(标题|名称|名字|title|name)$/i;
const SUMMARY = /^(事件概述|摘要|概述|简介|说明|summary|description|overview)$/i;
const DATE = /^(发布时间|发布日期|日期|时间|published_at|published|date|time)$/i;
const SOURCE = /来源|链接|source|url|link/i;

/** Only real web/local source URLs become actionable; never execute model text. */
export function reportSourceLinks(text: string): string[] {
  const candidates = text.match(/(?:https?:\/\/|local:\/\/)[^\s<>\[\]"')]+/gi) ?? [];
  return [...new Set(candidates.map(value => value.replace(/[，。；,;]+$/, "")).filter(value => {
    try {
      const url = new URL(value);
      return ["http:", "https:", "local:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password;
    } catch { return false; }
  }))];
}

export function reportRows(table: TableSchema, cells: Record<string, CoverageCell>): ReportRow[] {
  return table.entities.map(entity => {
    const fields = table.attributes.map(name => {
      const cell = cells[cellKey(table.table_id, entity, name)];
      const text = (Array.isArray(cell?.value) ? cell.value.join("\n\n") : cell?.value ?? "").trim();
      return { name, text, status: cell?.status ?? "missing", conflict: !!cell?.has_conflict, links: SOURCE.test(name) ? reportSourceLinks(text) : [] };
    });
    const available = fields.filter(field => field.text && field.status !== "missing");
    const title = available.find(field => TITLE.test(field.name))?.text || rowLabel(entity);
    const summary = (available.find(field => SUMMARY.test(field.name)) ?? available.find(field => !TITLE.test(field.name) && !DATE.test(field.name) && !SOURCE.test(field.name)))?.text ?? "";
    return {
      id: entity, title, summary: summary.slice(0, 160),
      date: available.find(field => DATE.test(field.name))?.text ?? "",
      fields, sources: [...new Set(available.flatMap(field => field.links))],
      needsReview: fields.some(field => field.conflict || field.status === "uncertain" || field.status === "hard_cell"),
    };
  });
}
