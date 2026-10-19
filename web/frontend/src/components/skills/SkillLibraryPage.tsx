"use client";

import { useWorkspaceBase } from "@/hooks/useWorkspaceBase";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, ArrowUpRight, Blocks, Check, Code2, FileText, Globe2, Loader2, Plus, Search, X } from "lucide-react";
import { getSkillLibraryDetail, getSkillLibraryFile, querySkillLibrary, type SkillLibraryQuery, type SkillLibraryResults, type SkillLibraryItem, type SkillLibraryDetail } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";

function subscribeWidth(callback: () => void) {
  window.addEventListener("resize", callback);
  return () => window.removeEventListener("resize", callback);
}
const readWidth = () => window.innerWidth;
const serverWidth = () => 0;

function SkillReader({ item, zh, onClose }: { item: SkillLibraryItem; zh: boolean; onClose: () => void }) {
  const [detail, setDetail] = useState<SkillLibraryDetail | null>(null);
  const [file, setFile] = useState("");
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  useEffect(() => {
    let stale = false;
    getSkillLibraryDetail(item.category, item.name).then((value) => { if (!stale) setDetail(value); }).catch((e) => { if (!stale) setError(e.message); });
    return () => { stale = true; };
  }, [item.category, item.name]);
  useEffect(() => {
    if (!file) return;
    let stale = false;
    getSkillLibraryFile(item.category, item.name, file).then((value) => { if (!stale) setContent(value.content); }).catch((e) => { if (!stale) setError(e.message); });
    return () => { stale = true; };
  }, [file, item.category, item.name]);
  return <section className="min-w-0 overflow-hidden rounded-2xl border border-line bg-surface lg:sticky lg:top-6" aria-label={zh ? "技能详情" : "Skill details"}>
    <div className="border-b border-line p-5">
      <div className="mb-3 flex items-center justify-between"><span className="text-[11px] font-medium uppercase tracking-wider text-accent-ink">{item.category}</span><button autoFocus type="button" aria-label={zh ? "关闭详情" : "Close details"} onClick={onClose} className="rounded-lg p-1.5 text-ink-faint hover:bg-surface-2"><X size={16} /></button></div>
      <h2 className="break-all text-[19px] font-semibold text-ink">{item.name}</h2>
      <p className="mt-2 text-[12px] leading-6 text-ink-dim">{item.description}</p>
    </div>
    {detail && <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
      <button type="button" onClick={() => { setFile(""); setContent(null); setError(""); }} className={`rounded-lg px-3 py-1.5 text-[12px] ${!file ? "bg-accent/10 text-accent-ink" : "text-ink-dim hover:bg-surface-2"}`}>{zh ? "使用说明" : "Instructions"}</button>
      <label className="flex min-w-0 flex-1 items-center gap-2 text-[12px] text-ink-dim"><Code2 size={14} /><select aria-label={zh ? "查看技能文件" : "View skill files"} value={file} onChange={(e) => { setFile(e.target.value); setContent(null); setError(""); }} className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-2 py-1.5 outline-none focus:border-accent"><option value="">{zh ? "查看文件…" : "Browse files…"}</option>{detail.files.map((path) => <option key={path} value={path}>{path}</option>)}</select></label>
    </div>}
    <div className="max-h-[70vh] overflow-auto p-5">
      {error ? <p role="alert" className="text-[12px] text-err">{error}</p> : !detail || file && content === null ? <div role="status" className="flex items-center gap-2 text-[12px] text-ink-faint"><Loader2 size={14} className="animate-spin" />{zh ? "正在读取…" : "Loading…"}</div> : file ? <pre className="whitespace-pre-wrap break-all font-mono text-[12px] leading-6 text-ink-dim">{content}</pre> : <div className="space-y-3 break-words text-[13px] leading-7 text-ink-dim [&_a]:text-accent-ink [&_a]:underline [&_code]:rounded [&_code]:bg-surface-2 [&_code]:px-1 [&_h1]:text-xl [&_h1]:font-semibold [&_h1]:text-ink [&_h2]:mt-6 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-ink [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_pre]:overflow-auto [&_pre]:rounded-xl [&_pre]:bg-paper [&_pre]:p-3 [&_table]:block [&_table]:overflow-auto [&_td]:border [&_td]:border-line [&_td]:p-2 [&_th]:border [&_th]:border-line [&_th]:p-2 [&_ul]:list-disc">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span className="text-ink-faint">{alt}</span>, a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{detail.body}</ReactMarkdown>
      </div>}
    </div>
  </section>;
}

export default function SkillLibraryPage() {
  const base = useWorkspaceBase();
  const { uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const [results, setResults] = useState<SkillLibraryResults>({ items: [], total: 0, page: 1, pages: 0, page_size: 24, counts: {} });
  const [request, setRequest] = useState<SkillLibraryQuery>({ q: "", category: "all", page: 1, page_size: 24 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<SkillLibraryItem | null>(null);
  const width = useSyncExternalStore(subscribeWidth, readWidth, serverWidth);
  const columnCount = width >= 1280 ? (selected ? 2 : 4) : width >= 1024 ? (selected ? 1 : 3) : width >= 640 ? 2 : 1;
  const [attempt, setAttempt] = useState(0);
  const [append, setAppend] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const loadingMore = useRef(false);
  useEffect(() => {
    let stale = false;
    querySkillLibrary(request).then((value) => { if (!stale) { setResults((previous) => append ? { ...value, items: [...previous.items, ...value.items.filter((item) => !previous.items.some((old) => old.category === item.category && old.name === item.name))] } : value); setError(""); } }).catch((e) => { if (!stale) setError(e.message); }).finally(() => { if (!stale) { loadingMore.current = false; setLoading(false); } });
    return () => { stale = true; };
  }, [attempt, request, append]);
  useEffect(() => {
    const sentinel = moreRef.current;
    if (!sentinel || loading || error || selected || results.page >= results.pages) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || loadingMore.current) return;
      loadingMore.current = true;
      setAppend(true);
      setLoading(true);
      setRequest((previous) => ({ ...previous, page: results.page + 1 }));
    }, { rootMargin: "300px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loading, error, selected, results.page, results.pages]);
  const updateQuery = (patch: Partial<SkillLibraryQuery>) => {
    loadingMore.current = true;
    setAppend(false);
    setLoading(true);
    setError("");
    setSelected(null);
    setRequest((previous) => ({ ...previous, page: 1, ...patch }));
  };
  const pageNumbers = Array.from(new Set([1, results.pages, results.page - 1, results.page, results.page + 1]))
    .filter((page) => page >= 1 && page <= results.pages).sort((a, b) => a - b);
  return <main className="mx-auto min-h-screen max-w-[1440px] px-5 py-7 sm:px-10">
    <Link href={base || "/"} className="mb-9 inline-flex items-center gap-1.5 text-[12px] text-ink-dim hover:text-ink"><ArrowLeft size={14} />{zh ? "返回搜索" : "Back to search"}</Link>
    <header className="mb-8 flex flex-wrap items-end justify-between gap-5">
      <div><div className="mb-3 flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-accent-ink"><Blocks size={14} /> SEARCHOS SKILLS</div><h1 className="text-[30px] font-semibold tracking-tight text-ink">{zh ? "技能库" : "Skill library"}</h1><p className="mt-2 text-[13px] text-ink-dim">{zh ? "浏览可复用能力，查看使用说明与实现文件。" : "Explore reusable capabilities, instructions, and implementation files."}</p></div>
      <Link href={`${base}/skills/new`} className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-3 text-[13px] font-medium text-white shadow-sm hover:brightness-110"><Plus size={16} />{zh ? "创建技能" : "Create skill"}</Link>
    </header>
    <div className="mb-7 flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap gap-1 rounded-xl bg-surface-2 p-1" aria-label={zh ? "技能分类" : "Categories"}>{["all", "access", "strategy", "orchestrator"].map((value) => <button key={value} type="button" aria-pressed={request.category === value} onClick={() => updateQuery({ category: value })} className={`rounded-lg px-3 py-2 text-[12px] transition ${request.category === value ? "bg-surface font-medium text-ink shadow-sm" : "text-ink-dim hover:text-ink"}`}>{value === "all" ? (zh ? "全部" : "All") : value}<span className="ml-2 text-[10px] tabular-nums text-ink-faint">{results.counts[value] ?? 0}</span></button>)}</div>
      <form onSubmit={(event) => { event.preventDefault(); updateQuery({ q: query.trim() }); }} className="input-surface flex w-full items-center gap-2 rounded-xl border border-line bg-surface p-1.5 pl-3 text-ink-faint sm:w-[380px]">
        <Search size={15} /><input aria-label={zh ? "查询技能" : "Search skills"} maxLength={500} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "查询名称、能力或说明正文…" : "Search names, capabilities, or instructions…"} className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-ink-faint" />
        {(query || request.q) && <button type="button" aria-label={zh ? "清空查询" : "Clear search"} onClick={() => { setQuery(""); updateQuery({ q: "" }); }} className="rounded p-1 hover:bg-surface-2"><X size={13} /></button>}
        <button type="submit" className="rounded-lg bg-accent px-3 py-2 text-[12px] text-white hover:brightness-110">{zh ? "查询" : "Search"}</button>
      </form>
    </div>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 text-[12px] text-ink-dim">
      <span aria-live="polite">{loading && !append ? (zh ? "正在查询…" : "Searching…") : request.q ? (zh ? `“${request.q}” · ${results.total} 个结果` : `“${request.q}” · ${results.total} results`) : (zh ? `共 ${results.total} 个技能` : `${results.total} skills`)}</span>
      <label className="flex items-center gap-2">{zh ? "每页" : "Per page"}<select value={request.page_size} onChange={(event) => updateQuery({ page_size: Number(event.target.value) })} className="rounded-lg border border-line bg-surface px-2 py-1.5">{[12, 24, 48].map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
    </div>
    {error && <p role="alert" className="mb-5 rounded-xl bg-err/5 p-4 text-[13px] text-err">{error}<button onClick={() => { setLoading(true); setAttempt((n) => n + 1); }} className="ml-4 underline">{zh ? "重试" : "Retry"}</button></p>}
    {loading && !append ? <p role="status" className="flex items-center gap-2 py-12 text-[13px] text-ink-dim"><Loader2 size={16} className="animate-spin" />{zh ? "正在读取技能库…" : "Loading library…"}</p> : <div className={`grid items-start gap-6 ${selected ? "lg:grid-cols-[minmax(0,1fr)_minmax(380px,0.95fr)]" : ""}`}>
      <div className="min-w-0">
        {!results.items.length && !error && <div className="rounded-2xl border border-dashed border-line-strong p-12 text-center text-[13px] text-ink-dim"><Blocks className="mx-auto mb-4 text-ink-faint" size={26} />{request.q || request.category !== "all" ? (zh ? "没有匹配的技能，试试其他关键词或分类。" : "No matching skills. Try another search or category.") : (zh ? "技能库还是空的，创建第一个技能吧。" : "Your library is empty. Create your first skill.")}</div>}
        <div className="grid items-start gap-4" style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}>{Array.from({ length: columnCount }, (_, column) => <div key={column} className="min-w-0">{results.items.filter((_, index) => index % columnCount === column).map((item) => {
          const chosen = selected?.category === item.category && selected.name === item.name;
          return <button key={`${item.category}/${item.name}`} type="button" aria-pressed={chosen} onClick={() => setSelected(item)} className={`group mb-4 inline-block w-full min-w-0 break-inside-avoid rounded-2xl border bg-surface p-5 text-left transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-accent ${chosen ? "border-accent/60 ring-2 ring-accent/10" : "border-line hover:border-line-strong"}`}>
            <div className="mb-5 flex items-center justify-between"><span className="rounded-lg bg-accent/5 p-2 text-accent-ink">{item.category === "access" ? <Globe2 size={17} /> : <FileText size={17} />}</span><span className="text-[10px] text-ink-faint">{item.category}</span></div>
            <h2 className="break-words text-[13px] font-semibold text-ink" title={item.name}>{item.name}</h2><p className="mt-2 text-[12px] leading-5 text-ink-dim">{item.description || (zh ? "暂无描述" : "No description")}</p>
            <div className="mt-5 flex items-center justify-between border-t border-line pt-3 text-[10px] text-ink-faint"><span className="flex items-center gap-1">{item.package_format === "portable" && <Check size={11} />}{item.package_format === "portable" ? "SKILL.md" : (zh ? "旧版格式" : "Legacy")}</span><span className="flex items-center gap-1 group-hover:text-accent-ink">{zh ? "查看" : "View"}<ArrowUpRight size={12} /></span></div>
          </button>;
        })}</div>)}</div>
        <div ref={moreRef} className="flex min-h-16 items-center justify-center gap-2 py-5 text-[12px] text-ink-faint" role="status">
          {loading && append ? <><Loader2 size={14} className="animate-spin" />{zh ? "正在加载更多技能…" : "Loading more skills…"}</> : results.page < results.pages ? (zh ? "继续向下滚动，自动加载更多" : "Scroll down to load more") : results.total > 0 ? (zh ? "已到最后一页" : "You have reached the last page") : null}
        </div>
        {results.total > 0 && <nav aria-label={zh ? "技能分页" : "Skill pagination"} className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5 text-[12px] text-ink-dim">
          <span>{zh ? `已展示 ${results.items.length} 个 · 共 ${results.total} 个 · 当前第 ${results.page} / ${results.pages} 页` : `${results.total} skills · Page ${results.page} / ${results.pages}`}</span>
          <div className="flex flex-wrap items-center gap-1">
            <button type="button" disabled={loading || results.page <= 1} onClick={() => updateQuery({ page: results.page - 1 })} className="rounded-lg px-2 py-2 hover:bg-surface disabled:opacity-30">{zh ? "上一页" : "Previous"}</button>
            {pageNumbers.map((page, index) => <span key={page} className="flex items-center gap-1">{index > 0 && page - pageNumbers[index - 1] > 1 && <span className="px-1">…</span>}<button type="button" disabled={loading} aria-label={zh ? `第 ${page} 页` : `Page ${page}`} aria-current={page === results.page ? "page" : undefined} onClick={() => updateQuery({ page })} className={`min-w-8 rounded-lg px-2 py-2 ${page === results.page ? "bg-accent text-white" : "hover:bg-surface"}`}>{page}</button></span>)}
            <button type="button" disabled={loading || results.page >= results.pages} onClick={() => updateQuery({ page: results.page + 1 })} className="rounded-lg px-2 py-2 hover:bg-surface disabled:opacity-30">{zh ? "下一页" : "Next"}</button>
          </div>
        </nav>}

      </div>
      {selected && <div className="fixed inset-0 z-50 overflow-auto bg-paper p-4 lg:static lg:z-auto lg:contents lg:bg-transparent lg:p-0"><SkillReader key={`${selected.category}/${selected.name}`} item={selected} zh={zh} onClose={() => setSelected(null)} /></div>}
    </div>}
  </main>;
}
