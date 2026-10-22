"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpRight, ChevronLeft, ChevronRight, Layers3 } from "lucide-react";
import type { CoverageMap, EvidenceNode, TableSchema } from "@/lib/types";
import { reportRows } from "@/lib/mobileReportPreview";
import Answer from "@/components/conversation/Answer";
import MobileSheet from "./MobileSheet";
import s from "./mobile-assistant.module.css";

export default function MobileReportCards({ table, cells, evidence, onOpenSource }: {
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
  const label = table.table_label || "研究摘要";
  const sourceName = (url: string) => url.startsWith("local://") ? "本地资料" : new URL(url).hostname.replace(/^www\./, "");
  const toggle = () => setExpanded(value => !value);

  return <section className={s.digest} aria-label={label}>
    <button ref={header} className={s.digestHeader} type="button" aria-expanded={expanded} aria-controls={listId} onClick={toggle}>
      <span className={s.digestIcon}><Layers3 size={22} /></span>
      <span className={s.digestHeading}><b>{label}</b><small>{expanded ? "全部条目" : `精选预览 · 共 ${rows.length} 条`}</small></span>
      <span className={s.digestCount}>{rows.length}</span><ChevronRight size={17} className={expanded ? s.digestChevronOpen : undefined} />
    </button>
    <div id={listId} className={s.digestRows}>
      {visible.map((row, rowIndex) => <button type="button" className={s.digestRow} key={row.id} aria-label={`查看条目 ${rowIndex + 1}：${row.title}`} onClick={() => setSelectedId(row.id)}>
        <span className={s.digestNumber}>{String(rowIndex + 1).padStart(2, "0")}</span>
        <span className={s.digestRowBody}><b>{row.title}</b>{row.summary && <span className={s.digestExcerpt}>{row.summary}</span>}
          <span className={s.digestMeta}>{row.date && <span>{row.date}</span>}{row.sources[0] && <span>{sourceName(row.sources[0])}</span>}{row.needsReview && <em>有信息待核实</em>}</span>
        </span><ChevronRight size={16} className={s.digestRowArrow} />
      </button>)}
    </div>
    {rows.length > 3 && <button className={s.digestMore} type="button" aria-expanded={expanded} aria-controls={listId} onClick={() => { if (expanded) header.current?.scrollIntoView({ block: "nearest" }); toggle(); }}>
      {expanded ? "收起条目" : `展开全部 ${rows.length} 个条目`}{expanded ? <ArrowUp size={15} /> : <ArrowDown size={15} />}
    </button>}
    {selected && <MobileSheet title="条目详情" subtitle={`${label} · ${index + 1} / ${rows.length}`} onClose={() => setSelectedId(null)} footer={<div className={s.digestPager}>
      <button disabled={index === 0} onClick={() => setSelectedId(rows[index - 1].id)}><ChevronLeft size={17} />上一条</button><span>{index + 1} / {rows.length}</span><button disabled={index === rows.length - 1} onClick={() => setSelectedId(rows[index + 1].id)}>下一条<ChevronRight size={17} /></button>
    </div>}>
      <div ref={detail} className={s.digestDetail} key={selected.id}>
        <span className={s.digestDetailTag}>条目 {String(index + 1).padStart(2, "0")}</span><h3>{selected.title}</h3>
        {selected.fields.filter(field => field.text !== selected.title || field.conflict || field.status !== "filled").map(field => <section key={field.name} className={s.digestField}>
          <h4>{field.name}{field.conflict ? <span>信息有冲突</span> : field.status === "uncertain" || field.status === "hard_cell" ? <span>待核实</span> : null}</h4>
          {!field.text || field.status === "missing" ? <p className={s.caption}>暂无信息</p> : field.links.length ? <div className={s.digestSources}>{field.links.map(url => url.startsWith("local://") ? <button key={url} onClick={() => { setSelectedId(null); onOpenSource(url); }}>{sourceName(url)}<ArrowUpRight size={16} /></button> : <a key={url} href={url} target="_blank" rel="noopener noreferrer"><span>{sourceName(url)}<small>{url}</small></span><ArrowUpRight size={16} /></a>)}</div> :
            <Answer markdown={field.text} localSources={evidence.map(node => node.source).filter(source => source.startsWith("local://"))} evidenceSources={Object.fromEntries(evidence.filter(node => !node.status || node.status === "active").map(node => [node.id, node.source_urls?.length ? node.source_urls : node.source]))} onOpenLocalSource={source => { setSelectedId(null); onOpenSource(source); }} />}
        </section>)}
      </div>
    </MobileSheet>}
  </section>;
}
