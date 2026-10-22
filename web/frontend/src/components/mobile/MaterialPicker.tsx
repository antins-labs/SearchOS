"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, FileText, FolderOpen, Loader2, Search, Upload } from "lucide-react";
import { mobileSourceSelection } from "@/lib/mobileSources";
import { cancelLocalIndexJob, retryLocalIndexJob, localDocumentOriginalUrl, localDocumentPreviewUrl, listLocalDocuments } from "@/lib/api";
import type { LocalDocument, SourceSelection } from "@/lib/types";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";
import MobileSheet from "./MobileSheet";
import s from "./mobile-assistant.module.css";

export default function MaterialPicker({ controller, mode, onClose, onApply, onUpload, initialSelection }: {
  controller: LocalLibraryController;
  mode: "local" | "hybrid";
  initialSelection?: SourceSelection;
  onClose: () => void;
  onApply: (selection: SourceSelection) => void;
  onUpload: () => void;
}) {
  const [draftLibraryId, setLibraryId] = useState(initialSelection?.local?.library_id ?? controller.libraryId ?? "");
  const libraryId = draftLibraryId || controller.libraryId || controller.libraries[0]?.library_id || "";
  const [selected, setSelected] = useState(initialSelection?.local?.document_ids ?? controller.selectedDocumentIds);
  const [documents, setDocuments] = useState<LocalDocument[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(!!libraryId);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<LocalDocument | null>(null);
  const [actionError, setActionError] = useState("");
  const [changedLibrary, setChangedLibrary] = useState(false);
  useEffect(() => {
    if (!libraryId) return;
    let alive = true;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      await listLocalDocuments(libraryId).then(items => {
      if (!alive) return;
      setDocuments(items);
      setSelected(ids => ids.filter(id => items.some(item => item.document_id === id && item.searchable)));
      setError(null);
    }).catch(cause => { if (alive) setError(cause instanceof Error ? cause.message : "无法读取资料，请重试。"); })
      .finally(() => { pending = false; if (alive) setLoading(false); });
    };
    void refresh();
    // The picker stays open during upload/indexing, including a plan's picker.
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 3000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [libraryId, revision, controller.uploading]);
  const filtered = useMemo(() => documents.filter(doc => doc.name.toLowerCase().includes(query.trim().toLowerCase())), [documents, query]);
  const toggle = (id: string) => setSelected(ids => ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id]);
  const validIds = selected.filter(id => documents.some(doc => doc.document_id === id && doc.searchable));
  const act = async (operation: () => Promise<unknown>) => { if (busy) return; setBusy(true); setActionError(""); try { await operation(); setRevision(value => value+1); setDetail(null); } catch (e) { setActionError(e instanceof Error ? e.message : "操作失败"); } finally { setBusy(false); } };
  if (detail) return <MobileSheet title={detail.name} subtitle="资料详情" onClose={() => setDetail(null)}>
    <p className={s.caption}>{detail.kind.toUpperCase()} · {formatBytes(detail.size_bytes)} · {detail.searchable ? "可用于研究" : "尚未就绪"}</p>
    <div className={s.cardButtons}><a target="_blank" rel="noopener noreferrer" href={localDocumentPreviewUrl(libraryId, detail.document_id, detail.kind)}>查看内容</a><a target="_blank" rel="noopener noreferrer" href={localDocumentOriginalUrl(libraryId, detail.document_id)}>打开原文件</a>
    {detail.index_job && ["failed", "cancelled"].includes(detail.index_job.status) && <button disabled={busy} onClick={() => void act(() => retryLocalIndexJob(libraryId, detail.index_job!.job_id))}>重试处理</button>}
    {detail.index_job && ["queued", "running"].includes(detail.index_job.status) && <button disabled={busy} onClick={() => void act(() => cancelLocalIndexJob(libraryId, detail.index_job!.job_id))}>停止处理</button>}
    <button disabled={busy} onClick={() => { if (window.confirm(`删除“${detail.name}”？引用此资料的计划可能需要重新选择资料。`)) void act(async () => { await controller.deleteDocument(libraryId, detail.document_id); setSelected(ids => ids.filter(id => id !== detail.document_id)); }); }}>删除资料</button></div>
    {actionError && <p className={s.error} role="alert">{actionError}</p>}
  </MobileSheet>;
  return <MobileSheet title="选择资料" onClose={onClose} footer={<>
    <span className={s.selectionCount}>已选 <b>{validIds.length}</b> 份</span>
    <button className={s.primaryButton} disabled={!validIds.length || loading || !!error} onClick={() => { const selection = mobileSourceSelection(mode, libraryId, documents, validIds); if (selection) onApply(selection); }}>确认选择 <Check size={16} /></button>
  </>}>
    <button className={s.uploadTile} onClick={() => { if (libraryId) controller.setLibraryId(libraryId); onUpload(); }} disabled={controller.uploading}><span className={s.tileIcon}><Upload size={21} /></span><span><b>上传新资料</b><small>PDF、文档、表格或图片</small></span><span>＋</span></button>
    {controller.uploads.length > 0 && <div className={s.uploadProgress} role="status">{controller.uploads.map(item => <span key={item.id}><FileText size={13} />{item.name}<b>{item.status === "ready" ? "已就绪" : item.status === "error" || item.status === "index_error" ? "处理失败" : item.status === "index_cancelled" ? "已取消" : item.status === "uploading" ? `${item.progress}%` : "处理中"}</b></span>)}</div>}
    <label className={s.searchBox}><Search size={17} /><input aria-label="搜索资料" placeholder="搜索资料名称" value={query} onChange={event => setQuery(event.target.value)} /></label>
    {controller.libraries.length > 0 && <label className={s.fieldLabel}>资料库<select aria-label="选择资料库" value={libraryId} onChange={event => { setLibraryId(event.target.value); setDocuments([]); setSelected([]); setLoading(true); setError(null); setChangedLibrary(true); }}>{controller.libraries.map(lib => <option key={lib.library_id} value={lib.library_id}>{lib.name}</option>)}</select></label>}
    <details className={s.libraryTools}><summary>管理资料库</summary><div className={s.cardButtons}><button disabled={busy} onClick={() => { const name = window.prompt("新资料库名称"); if (name?.trim()) void act(async () => { await controller.createLibrary(name.trim()); setLibraryId(""); setSelected([]); }); }}>新建资料库</button>{libraryId && <button disabled={busy} onClick={() => { const name = window.prompt("资料库名称", controller.libraries.find(item => item.library_id === libraryId)?.name); if (name?.trim()) void act(() => controller.renameLibrary(libraryId, name.trim())); }}>重命名资料库</button>}</div></details>
    {actionError && <p className={s.error} role="alert">{actionError}</p>}
    {changedLibrary && <p className={s.caption}>已切换资料库，待选项已清空。每次可使用一个库中的资料。</p>}
    {loading || controller.loading && !libraryId ? <div role="status" className={s.empty}><Loader2 size={25} className={s.spin} /><p>正在读取资料…</p></div> : error || controller.error && !libraryId ? <div role="alert" className={s.error}><p>{error ?? controller.error}</p><button onClick={() => { if (!libraryId) { onClose(); return; } setLoading(true); setRevision(value => value + 1); }}>{libraryId ? "重新加载" : "返回"}</button></div> : !documents.length ? <div className={s.empty}><FolderOpen size={36} /><h3>给助理一点背景资料</h3><p>上传材料后，可以让助理归纳重点、核对信息，或结合网络继续研究。</p></div> : <>
      <div className={s.sectionLabel}><span>{query ? "搜索结果" : "库中资料"} · {filtered.length}</span><button onClick={() => setSelected(ids => [...new Set([...ids, ...filtered.filter(doc => doc.searchable).map(doc => doc.document_id)])])}>全选可用资料</button>{selected.length > 0 && <button onClick={() => setSelected([])}>清空</button>}</div>
      {!filtered.length && <p className={s.empty}>没有匹配的资料，试试其他关键词。</p>}
      <div className={s.documentList}>{filtered.map(doc => <div className={s.documentWrap} key={doc.document_id}><label className={`${s.document} ${selected.includes(doc.document_id) ? s.documentSelected : ""}`}>
        <span className={s.documentIcon}><FileText size={21} /></span><span className={s.documentText}><b>{doc.name}</b><small>{doc.kind.toUpperCase()} · {formatBytes(doc.size_bytes)} · {doc.searchable ? "可用于研究" : doc.index_job?.status === "failed" || doc.status === "failed" ? "处理失败" : doc.index_job?.status === "cancelled" ? "已取消处理" : "处理中"}</small></span><input type="checkbox" aria-label={`选择 ${doc.name}`} disabled={!doc.searchable} checked={selected.includes(doc.document_id)} onChange={() => toggle(doc.document_id)} />
      </label><button className={s.textButton} onClick={() => setDetail(doc)} aria-label={`查看资料详情 ${doc.name}`}>查看详情</button></div>)}</div>
      <button className={s.textButton} onClick={() => { setLoading(true); setRevision(value => value + 1); }}>刷新处理状态</button>
    </>}
  </MobileSheet>;
}
function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }
