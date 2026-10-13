"use client";

import "./knowledgeCards.css";

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Ban,
  BookOpen,
  Check,
  Database,
  ExternalLink,
  FileText,
  FileUp,
  FolderTree,
  FolderOpen,
  LibraryBig,
  Loader2,
  ListTree,
  List,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  X,
} from "lucide-react";

import DocumentIndexView from "@/components/local/DocumentIndexView";
import KnowledgeMutationDialog from "@/components/local/KnowledgeMutationDialog";
import dynamic from "next/dynamic";

const KnowledgeGraphView = dynamic(() => import("@/components/local/KnowledgeGraphView"), {
  loading: () => <div className="grid h-full place-items-center text-sm text-ink-faint">正在加载图谱…</div>,
});
import { FileBadge } from "./knowledgeAppearance";
import KnowledgeListView from "@/components/local/KnowledgeListView";
import useDialogFocus from "@/hooks/useDialogFocus";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";
import {
  getLocalLibraryGraph,
  localDocumentOriginalUrl,
  localDocumentPreviewUrl,
  setLocalDocumentTopics,
  retryLocalTopicRecaps,
  editLocalDocument,
  saveLocalTopic,
  deleteLocalTopic,
} from "@/lib/api";
import type { LocalDocument, LocalGraphNode, LocalLibraryGraph } from "@/lib/types";

const ACCEPTED_FILES = ".md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.csv,.tsv,.json,.jsonl,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff";

function bytesLabel(bytes = 0): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

function statusLabel(status?: string): string {
  if (status === "ready" || status === "completed") return "就绪";
  if (status === "partial") return "部分完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  if (status === "queued") return "排队中";
  if (status === "running") return "处理中";
  return "待处理";
}

function documentIndexProgress(document: LocalDocument) {
  const completed = document.index_job?.recap_segments_completed
    ?? document.recap_segments_completed;
  const total = document.index_job?.recap_segments_total
    ?? document.recap_segments_total;
  const failed = document.recap_status === "failed" || document.index_job?.status === "failed";
  const active = document.index_job?.status === "queued" || document.index_job?.status === "running";
  return {
    completed,
    total,
    failed,
    percent: total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0,
    indeterminate: total === 0 && active && !failed,
    label: failed ? "Recap 生成失败"
      : active ? "正在生成 Recap" : "Recap 已生成",
  };
}

function DocumentIndexProgress({ document }: { document: LocalDocument }) {
  const progress = documentIndexProgress(document);
  return (
    <div className="rounded-lg border border-line bg-paper px-2.5 py-2">
      <div className="mb-1.5 flex items-center justify-between gap-2 text-[10.5px]">
        <span className="text-ink-dim">{progress.label}</span>
        {progress.total > 0 && (
          <span className="tabular-nums text-ink-faint">
            {progress.completed}/{progress.total} segments
          </span>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="Recap 生成进度"
        aria-valuemin={0}
        aria-valuemax={progress.total || undefined}
        aria-valuenow={progress.total ? progress.completed : undefined}
        className="h-1.5 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-300 ${progress.failed ? "bg-err" : "bg-accent"} ${progress.indeterminate ? "w-full animate-pulse" : ""}`}
          style={progress.indeterminate ? undefined : { width: `${progress.percent}%` }}
        />
      </div>
    </div>
  );
}

interface Props {
  controller: LocalLibraryController;
  onClose: () => void;
}

type MutationTarget = {
  kind: "library" | "document" | "topic";
  libraryId: string;
  id?: string;
  name: string;
  summary?: string;
  deleting?: boolean;
};

export default function KnowledgeBasePanel({ controller, onClose }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [graphState, setGraphState] = useState<{
    libraryId: string;
    graph?: LocalLibraryGraph;
    error?: string;
  } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [viewMode, setViewMode] = useState<"graph" | "list">("list");
  const [newLibraryOpen, setNewLibraryOpen] = useState(false);
  const [newLibraryName, setNewLibraryName] = useState("");
  const [renamingLibraryId, setRenamingLibraryId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [graphRefresh, setGraphRefresh] = useState(0);
  const graphRevision = useRef(0);
  const [previewNode, setPreviewNode] = useState<LocalGraphNode | null>(null);
  const [indexNode, setIndexNode] = useState<LocalGraphNode | null>(null);
  const [mutatingDocumentId, setMutatingDocumentId] = useState<string | null>(null);
  const [graphMutationError, setGraphMutationError] = useState<string | null>(null);
  const [mutation, setMutation] = useState<MutationTarget | null>(null);
  const libraryId = controller.libraryId;
  const currentLibrary = controller.libraries.find((library) => library.library_id === libraryId) ?? null;
  const graph = libraryId && graphState?.libraryId === libraryId ? graphState.graph ?? null : null;
  const graphError = libraryId && graphState?.libraryId === libraryId ? graphState.error ?? null : null;
  const documentVersion = controller.documents.map((document) => (
    `${document.document_id}:${document.parse_status}:${document.recap_status}:${document.catalog_status}:${document.index_job?.status ?? "none"}`
  )).join("|");
  const hasPendingDocuments = controller.documents.some((document) => (
    document.parse_status === "pending"
    || document.recap_status === "pending"
    || document.catalog_status === "pending"
    || document.index_job?.status === "queued"
    || document.index_job?.status === "running"
  ));

  useDialogFocus({ containerRef: dialogRef, initialFocusRef: closeRef, onClose, active: !mutation });

  useEffect(() => {
    if (!libraryId) return;
    let alive = true;
    const revision = graphRevision.current;
    void getLocalLibraryGraph(libraryId)
      .then((value) => {
        if (!alive || revision !== graphRevision.current) return;
        setGraphState({ libraryId, graph: value });
        setSelectedId((current) => (
          current && value.nodes.some((node) => node.id === current)
            ? current
            : value.nodes.find((node) => node.node_type === "index")?.id ?? null
        ));
      })
      .catch((cause) => {
        if (alive) setGraphState({ libraryId, error: cause instanceof Error ? cause.message : String(cause) });
      });
    return () => { alive = false; };
  }, [currentLibrary?.name, documentVersion, graphRefresh, libraryId]);

  const hasPendingTopics = graph?.nodes.some((node) => node.node_type === "subindex" && node.recap_status === "pending");
  useEffect(() => {
    if (!libraryId || !hasPendingTopics) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const revision = graphRevision.current;
        const value = await getLocalLibraryGraph(libraryId);
        if (alive && revision === graphRevision.current) setGraphState({ libraryId, graph: value });
      } catch (cause) {
        if (alive) setGraphMutationError(cause instanceof Error ? cause.message : String(cause));
      }
      if (alive) timer = setTimeout(refresh, 1500);
    };
    timer = setTimeout(refresh, 1500);
    return () => { alive = false; clearTimeout(timer); };
  }, [libraryId, hasPendingTopics]);

  const refreshDocuments = controller.refreshDocuments;
  useEffect(() => {
    if (!libraryId || !hasPendingDocuments) return;
    const timer = globalThis.setInterval(() => {
      if (document.visibilityState === "visible") void refreshDocuments();
    }, 2000);
    return () => globalThis.clearInterval(timer);
  }, [refreshDocuments, hasPendingDocuments, libraryId]);

  const selectedNode = useMemo(() => (
    graph?.nodes.find((node) => node.id === selectedId) ?? null
  ), [graph, selectedId]);
  const selectedDocument = selectedNode?.document_id
    ? controller.documents.find((item) => item.document_id === selectedNode.document_id) ?? null
    : null;
  const selectedForQuestion = Boolean(
    selectedDocument && controller.selectedDocumentIds.includes(selectedDocument.document_id),
  );
  const previewUrl = previewNode?.document_id && libraryId
    ? localDocumentPreviewUrl(libraryId, previewNode.document_id, previewNode.document_kind ?? "")
    : "";
  const originalUrl = previewNode?.document_id && libraryId
    ? localDocumentOriginalUrl(libraryId, previewNode.document_id)
    : "";
  const graphCounts = useMemo(() => ({
    topics: graph?.nodes.filter((node) => node.node_type === "subindex").length ?? 0,
    documents: graph?.nodes.filter((node) => node.node_type === "document").length ?? 0,
  }), [graph]);

  const submitLibrary = async () => {
    const name = newLibraryName.trim();
    if (!name) return;
    setPreviewNode(null);
    setIndexNode(null);
    setQuery("");
    setSelectedId(null);
    await controller.createLibrary(name);
    setNewLibraryName("");
    setNewLibraryOpen(false);
  };

  const beginRename = (targetLibraryId: string, name: string) => {
    setRenamingLibraryId(targetLibraryId);
    setRenameValue(name);
  };

  const submitRename = async () => {
    if (!renamingLibraryId || !renameValue.trim()) return;
    try {
      await controller.renameLibrary(renamingLibraryId, renameValue);
      setRenamingLibraryId(null);
      setRenameValue("");
    } catch {
      // The shared controller exposes the API error in the panel alert.
    }
  };

  const updateDocumentTopics = async (documentId: string, subindexIds: string[]) => {
    if (!libraryId || mutatingDocumentId) return;
    setMutatingDocumentId(documentId);
    setGraphMutationError(null);
    try {
      const value = await setLocalDocumentTopics(libraryId, documentId, subindexIds);
      graphRevision.current += 1;
      setGraphState({ libraryId, graph: value });
      setSelectedId(`document:${documentId}`);
      await controller.refreshDocuments();
    } catch (cause) {
      setGraphMutationError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setMutatingDocumentId(null);
    }
  };

  const deleteDocumentTopic = (documentId: string, subindexId: string) => {
    const remaining = (graph?.edges ?? []).flatMap((edge) => {
      if (edge.target !== `document:${documentId}` || edge.relation !== "classifies") return [];
      const topic = graph?.nodes.find((node) => node.id === edge.source);
      return topic?.subindex_id && topic.subindex_id !== subindexId ? [topic.subindex_id] : [];
    });
    void updateDocumentTopics(documentId, remaining);
  };

  const saveMutation = async (name: string, summary: string) => {
    if (!mutation) return;
    const target = mutation;
    if (target.kind === "library") {
      await controller.deleteLibrary(target.libraryId);
      graphRevision.current += 1;
      setGraphRefresh((current) => current + 1);
      if (libraryId === target.libraryId) {
        setSelectedId(null); setPreviewNode(null); setIndexNode(null); setGraphState(null);
      }
      return;
    }
    const value = target.kind === "document"
      ? target.deleting
        ? await controller.deleteDocument(target.libraryId, target.id!)
        : await editLocalDocument(target.libraryId, target.id!, name)
      : target.deleting
        ? await deleteLocalTopic(target.libraryId, target.id!)
        : await saveLocalTopic(target.libraryId, name, summary, target.id);
    graphRevision.current += 1;
    setGraphState({ libraryId: target.libraryId, graph: value });
    setGraphRefresh((current) => current + 1);
    if (target.deleting) { setSelectedId(`index:${target.libraryId}`); setPreviewNode(null); setIndexNode(null); }
    else if (target.kind === "topic") {
      setSelectedId(value.nodes.find((node) => node.node_type === "subindex" && node.label === name)?.id ?? null);
    }
  };

  return (
    <div className="knowledge-panel fade-in fixed inset-0 z-[70] flex items-center justify-center bg-ink/25 p-0 dark:bg-black/55 sm:p-4" onMouseDown={() => { if (!mutation) onClose(); }}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="knowledge-base-title"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
        className="rise-in surface relative flex h-[100dvh] w-full flex-col overflow-hidden rounded-none shadow-2xl sm:h-[min(860px,94vh)] sm:max-w-[1600px] sm:rounded-2xl"
      >
        <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3 sm:px-5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-clay text-accent-ink"><Database size={17} /></span>
          <div className="mr-2 min-w-36">
            <h1 id="knowledge-base-title" className="font-semibold tracking-tight text-[19px] text-ink">知识库</h1>
            <p className="text-[11px] text-ink-faint">浏览文档、主题与索引</p>
          </div>
          {currentLibrary && <div className="min-w-0 max-w-64 rounded-lg border border-line bg-surface-2 px-3 py-1.5"><div className="text-[9px] uppercase tracking-wider text-ink-faint">当前知识库</div><div className="truncate text-[12px] font-medium text-ink">{currentLibrary.name}</div></div>}
          <button type="button" onClick={() => setNewLibraryOpen((value) => !value)} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-[12px] text-ink-dim hover:bg-surface-2"><Plus size={13} />新建资料库</button>
          <button type="button" disabled={!libraryId} onClick={() => libraryId && setMutation({ kind: "topic", libraryId, name: "", summary: "" })}
            className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-[12px] text-ink-dim hover:bg-surface-2 disabled:opacity-40"><Plus size={13} />新建主题</button>
          <button type="button" disabled={controller.uploading} onClick={() => inputRef.current?.click()} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-[12px] text-paper hover:opacity-90 disabled:opacity-40">
            {controller.uploading ? <Loader2 className="animate-spin" size={13} /> : <FileUp size={13} />}添加文档
          </button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED_FILES}
            className="hidden"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              event.target.value = "";
              void controller.uploadFiles(files);
            }}
          />
          <button type="button" onClick={() => { setGraphRefresh((value) => value + 1); void controller.refreshDocuments(); }} disabled={!libraryId || controller.loading} className="ml-auto rounded-lg p-2 text-ink-dim hover:bg-surface-2 disabled:opacity-40" aria-label="刷新知识库"><RefreshCw className={controller.loading ? "animate-spin" : ""} size={15} /></button>
          <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-2 text-ink-dim hover:bg-surface-2" aria-label="关闭知识库"><X size={17} /></button>
        </header>

        {newLibraryOpen && (
          <div className="flex items-center gap-2 border-b border-line bg-surface-2/50 px-5 py-2.5">
            <input
              autoFocus
              value={newLibraryName}
              onChange={(event) => setNewLibraryName(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void submitLibrary(); }}
              placeholder="资料库名称"
              maxLength={120}
              className="w-full max-w-sm rounded-lg border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
            />
            <button type="button" disabled={!newLibraryName.trim() || controller.creatingLibrary} onClick={() => { void submitLibrary(); }} className="rounded-lg bg-ink px-3 py-2 text-[12px] text-paper disabled:opacity-40">
              {controller.creatingLibrary ? "创建中…" : "创建"}
            </button>
            <button type="button" onClick={() => setNewLibraryOpen(false)} className="rounded-lg px-3 py-2 text-[12px] text-ink-faint hover:bg-surface-2">取消</button>
          </div>
        )}

        {controller.error && <div role="alert" className="border-b border-err/30 bg-err/5 px-5 py-2 text-[12px] text-err">{controller.error}</div>}

        {!libraryId ? (
          <div className="grid min-h-0 flex-1 place-items-center p-6 text-center">
            <div>
              <Database className="mx-auto mb-3 text-ink-faint" size={30} />
              <h2 className="text-[15px] font-medium text-ink">还没有资料库</h2>
              <p className="mt-1 text-[12px] text-ink-faint">创建资料库后，可上传文档并查看自动生成的索引图。</p>
              <button type="button" onClick={() => setNewLibraryOpen(true)} className="mt-4 rounded-lg bg-ink px-4 py-2 text-[12px] text-paper">创建资料库</button>
            </div>
          </div>
        ) : (
          <div className="relative flex min-h-0 flex-1 flex-col">
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
              <label className="flex min-w-52 flex-1 items-center gap-2 rounded-xl border border-line bg-paper px-3 py-2.5 text-ink-faint focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/10 sm:max-w-md">
                <Search size={13} />
                <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="查找主题或文档" placeholder="搜索标题、主题或摘要…" className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-ink-faint" />
                {query && <button type="button" onClick={() => setQuery("")} aria-label="清空知识库搜索"><X size={12} /></button>}
              </label>
              <span className="flex items-center gap-1 text-[11px] text-ink-faint"><FolderTree size={12} />{graphCounts.topics} 个主题</span>
              <span className="flex items-center gap-1 text-[11px] text-ink-faint"><FileText size={12} />{graphCounts.documents} 份文档</span>
              <span className="hidden text-[11px] text-ink-faint xl:inline">{viewMode === "graph" ? "点击节点逐层展开 · 拖文档关联主题" : "按主题浏览全部文档"}</span>
              <div className="flex rounded-lg border border-line bg-surface p-0.5" role="group" aria-label="知识库展示方式">
                <button type="button" onClick={() => setViewMode("list")} className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] ${viewMode === "list" ? "bg-ink text-paper" : "text-ink-dim hover:bg-surface-2"}`} aria-pressed={viewMode === "list"}><List size={12} />列表</button>
                <button type="button" onClick={() => setViewMode("graph")} className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] ${viewMode === "graph" ? "bg-ink text-paper" : "text-ink-dim hover:bg-surface-2"}`} aria-pressed={viewMode === "graph"}><Network size={12} />图谱</button>
              </div>
            </div>

            {graphMutationError && <div role="alert" className="border-b border-err/30 bg-err/5 px-4 py-2 text-[11px] text-err">{graphMutationError}</div>}

            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:grid lg:overflow-hidden lg:grid-cols-[180px_minmax(0,1fr)_280px] xl:grid-cols-[200px_minmax(0,1fr)_310px]">
              <nav className="max-h-40 shrink-0 overflow-y-auto border-b border-line bg-surface/60 p-3 lg:max-h-none lg:border-b-0 lg:border-r" aria-label="知识库列表">
                <div className="mb-2 flex items-center justify-between px-1">
                  <div>
                    <h2 className="text-[12px] font-medium text-ink">知识库列表</h2>
                    <p className="text-[10px] text-ink-faint">{controller.libraries.length} 个独立索引</p>
                  </div>
                  <button type="button" onClick={() => setNewLibraryOpen(true)} className="rounded-lg p-1.5 text-ink-faint hover:bg-paper hover:text-ink" aria-label="新建知识库"><Plus size={14} /></button>
                </div>
                <div className="space-y-1">
                  {controller.libraries.map((library) => {
                    const active = library.library_id === libraryId;
                    const renaming = renamingLibraryId === library.library_id;
                    if (renaming) {
                      return (
                        <div key={library.library_id} className="rounded-lg border border-accent bg-paper p-2">
                          <input
                            autoFocus
                            value={renameValue}
                            onChange={(event) => setRenameValue(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") void submitRename();
                              if (event.key === "Escape") setRenamingLibraryId(null);
                            }}
                            maxLength={120}
                            aria-label="新的知识库名称"
                            className="w-full rounded-md border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-accent"
                          />
                          <div className="mt-1.5 flex justify-end gap-1">
                            <button type="button" onClick={() => setRenamingLibraryId(null)} className="rounded px-2 py-1 text-[10px] text-ink-faint hover:bg-surface-2">取消</button>
                            <button type="button" disabled={!renameValue.trim() || controller.renamingLibraryId === library.library_id} onClick={() => { void submitRename(); }} className="rounded bg-ink px-2 py-1 text-[10px] text-paper disabled:opacity-40">{controller.renamingLibraryId === library.library_id ? "保存中…" : "保存"}</button>
                          </div>
                        </div>
                      );
                    }
                    return (
                      <div key={library.library_id} className={`group flex items-center rounded-lg border ${active ? "border-accent bg-clay" : "border-transparent hover:bg-paper"}`}>
                        <button
                          type="button"
                          onClick={() => {
                            if (active) return;
                            setPreviewNode(null);
                            setIndexNode(null);
                            setQuery("");
                            setSelectedId(null);
                            controller.setLibraryId(library.library_id);
                          }}
                          className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left"
                          aria-current={active ? "page" : undefined}
                        >
                          <Database size={13} className={active ? "text-accent-ink" : "text-ink-faint"} />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[12px] font-medium text-ink">{library.name}</span>
                            <span className="block truncate text-[10px] text-ink-faint">{active ? "当前浏览" : "点击打开"}</span>
                          </span>
                        </button>
                        <button type="button" onClick={() => beginRename(library.library_id, library.name)} className="mr-1 rounded-md p-1.5 text-ink-faint opacity-60 hover:bg-surface-2 hover:text-ink group-hover:opacity-100" aria-label={`重命名 ${library.name}`}><Pencil size={12} /></button>
                        <button type="button" disabled={controller.uploading} onClick={() => setMutation({ kind: "library", libraryId: library.library_id, name: library.name, deleting: true })}
                          className="mr-1 rounded-md p-1.5 text-ink-faint hover:bg-err/10 hover:text-err disabled:opacity-40" aria-label={`删除资料库 ${library.name}`}><Trash2 size={12} /></button>
                      </div>
                    );
                  })}
                </div>
                {libraryId && (
                  <details className="mt-4 rounded-lg border border-line bg-paper/70 p-2.5 text-[10px] leading-5 text-ink-faint">
                    <summary className="cursor-pointer font-medium text-ink-dim">索引存储位置</summary>
                    <div className="truncate font-mono">indexes/{libraryId}/</div>
                    <div className="pl-2 font-mono">├── INDEX.md</div>
                    <div className="pl-2 font-mono">├── subindexes/</div>
                    <div className="pl-2 font-mono">└── documents/</div>
                  </details>
                )}
              </nav>
              <section className="h-[60dvh] min-h-[28rem] shrink-0 overflow-hidden border-b border-line lg:h-auto lg:min-h-0 lg:border-b-0 lg:border-r" aria-label={viewMode === "graph" ? "知识库索引图" : "知识库索引列表"}>
                {!graph && !graphError && <div className="grid h-full place-items-center text-[13px] text-ink-faint"><span className="flex items-center gap-2"><Loader2 className="animate-spin" size={14} />读取索引图…</span></div>}
                {graphError && <div role="alert" className="grid h-full place-items-center p-6 text-[13px] text-err">{graphError}</div>}
                {graph && viewMode === "graph" && <KnowledgeGraphView
                  key={libraryId}
                  graph={graph}
                  query={deferredQuery}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onMoveDocument={(documentId, subindexId) => {
                    const existing = (graph?.edges ?? []).filter((edge) => edge.target === `document:${documentId}` && edge.relation === "classifies")
                      .map((edge) => graph?.nodes.find((node) => node.id === edge.source)?.subindex_id).filter((id): id is string => Boolean(id));
                    void updateDocumentTopics(documentId, subindexId ? Array.from(new Set([...existing, subindexId])) : []);
                  }}
                  onDeleteRelation={deleteDocumentTopic}
                  mutatingDocumentId={mutatingDocumentId}
                />}
                {graph && viewMode === "list" && <KnowledgeListView key={libraryId} graph={graph} query={deferredQuery} selectedId={selectedId} onSelect={setSelectedId} />}
              </section>

              <aside className="shrink-0 bg-surface/50 p-4 lg:min-h-0 lg:overflow-y-auto" aria-label="节点详情">
                {!selectedNode ? <p className="text-[13px] text-ink-faint">选择节点查看详情</p> : <>
                  <div className="mb-3 flex items-start gap-2">
                    {selectedNode.node_type === "document" ? <FileBadge kind={selectedNode.document_kind} filename={selectedNode.label} /> :
                      <span className={`mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-xl ${selectedNode.node_type === "index" ? "border border-line-strong bg-clay text-accent-ink" : "knowledge-folder-badge"}`}>
                        {selectedNode.node_type === "index" ? <LibraryBig size={23} strokeWidth={1.5} /> : <FolderOpen size={21} strokeWidth={1.5} />}
                      </span>}
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-wider text-ink-faint">{selectedNode.node_type === "index" ? "总索引" : selectedNode.node_type === "subindex" ? "主题索引" : "文档"}</div>
                      <h2 className="break-words text-[14px] font-medium text-ink">{selectedNode.label}</h2>
                    </div>
                  </div>
                  {selectedNode.original_name && selectedNode.original_name !== selectedNode.label && (
                    <p className="mb-2 break-all text-[11px] text-ink-faint">原文件：{selectedNode.original_name}</p>
                  )}
                  {selectedNode.node_type === "subindex" && selectedNode.recap_status === "pending" && (
                    <p className="mb-2 text-xs text-ink-faint" role="status">主题摘要正在更新，暂时显示上一版。</p>
                  )}
                  {selectedNode.node_type === "subindex" && selectedNode.recap_status === "failed" && (
                    <div className="mb-2 text-xs text-warn">
                      <p title={selectedNode.recap_error}>主题摘要更新失败，已保留上一版。</p>
                      <button type="button" className="mt-1 underline" onClick={async () => {
                        try { setGraphState({ libraryId, graph: await retryLocalTopicRecaps(libraryId) }); }
                        catch (cause) { setGraphMutationError(cause instanceof Error ? cause.message : String(cause)); }
                      }}>重新生成</button>
                    </div>
                  )}
                  <p className="mb-4 whitespace-pre-wrap text-[12px] leading-5 text-ink-dim">{selectedNode.summary || "暂无摘要"}</p>
                  {(selectedNode.node_type === "document" || selectedNode.node_type === "subindex") && <div className="mb-4 flex gap-2">
                    <button type="button" disabled={Boolean(mutatingDocumentId)} onClick={() => setMutation({
                      kind: selectedNode.node_type === "document" ? "document" : "topic", libraryId,
                      id: selectedNode.document_id ?? selectedNode.subindex_id, name: selectedNode.label,
                      summary: selectedNode.node_type === "subindex" ? selectedNode.summary : undefined,
                    })} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line px-2 py-2 text-xs text-ink-dim hover:bg-paper disabled:opacity-40"><Pencil size={12} />编辑{selectedNode.node_type === "document" ? "名称" : "主题"}</button>
                    <button type="button" disabled={Boolean(mutatingDocumentId)} onClick={() => setMutation({
                      kind: selectedNode.node_type === "document" ? "document" : "topic", libraryId,
                      id: selectedNode.document_id ?? selectedNode.subindex_id, name: selectedNode.label, deleting: true,
                    })} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-err hover:bg-err/10 disabled:opacity-40"><Trash2 size={12} />删除</button>
                  </div>}

                  {selectedNode.node_type === "index" && (
                    <div className="space-y-2 text-[12px] text-ink-dim">
                      <div className="flex justify-between border-b border-line pb-2"><span>主题</span><span>{graphCounts.topics}</span></div>
                      <div className="flex justify-between border-b border-line pb-2"><span>文档</span><span>{graphCounts.documents}</span></div>
                      <div className="pt-2 text-[11px] leading-5 text-ink-faint">虚线连接的文档已经可以问答，但仍在等待 Recap 和目录归类。</div>
                    </div>
                  )}

                  {selectedNode.node_type === "subindex" && (
                    <div className="space-y-2 text-[12px] text-ink-dim">
                      <div className="flex justify-between border-b border-line pb-2"><span>关联文档</span><span>{selectedNode.document_count ?? 0}</span></div>
                      <div className="flex justify-between border-b border-line pb-2"><span>索引字符</span><span>{selectedNode.character_count?.toLocaleString() ?? 0}</span></div>
                    </div>
                  )}

                  {selectedDocument && (
                    <div className="space-y-3">
                      <DocumentIndexProgress document={selectedDocument} />
                      <TopicMembershipEditor
                        key={`${selectedDocument.document_id}:${graph?.edges.filter((edge) => edge.target === selectedNode.id).map((edge) => edge.source).sort().join("|")}`}
                        topics={graph?.nodes.filter((node) => node.node_type === "subindex") ?? []}
                        selected={(graph?.edges ?? []).filter((edge) => edge.target === selectedNode.id && edge.relation === "classifies").map((edge) => edge.source.replace("subindex:", ""))}
                        busy={Boolean(mutatingDocumentId)}
                        onSave={(ids) => { void updateDocumentTopics(selectedDocument.document_id, ids); }}
                      />
                      <div className="grid grid-cols-3 gap-1.5 text-center text-[10px]">
                        {[["解析", selectedDocument.parse_status], ["Recap", selectedDocument.recap_status], ["目录", selectedDocument.catalog_status]].map(([label, status]) => (
                          <div key={label} className="rounded-lg bg-paper px-1.5 py-2"><div className="text-ink-faint">{label}</div><div className={status === "failed" ? "mt-0.5 text-err" : status === "ready" ? "mt-0.5 text-ok" : "mt-0.5 text-warn"}>{statusLabel(status)}</div></div>
                        ))}
                      </div>
                      <div className="space-y-1 text-[11px] text-ink-faint">
                        <div className="flex justify-between"><span>格式</span><span>{selectedDocument.kind.toUpperCase()}</span></div>
                        <div className="flex justify-between"><span>大小</span><span>{bytesLabel(selectedDocument.size_bytes)}</span></div>
                        <div className="flex justify-between"><span>版本</span><span className="font-mono">{selectedDocument.source_revision.slice(0, 12)}</span></div>
                      </div>
                      <button
                        type="button"
                        disabled={!selectedDocument.searchable}
                        onClick={() => {
                          const next = !selectedForQuestion;
                          controller.setDocumentSelected(selectedDocument.document_id, next);
                          if (next) controller.setMode("local");
                        }}
                        className={`flex w-full items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-[12px] ${selectedForQuestion ? "border-accent bg-clay text-accent-ink" : "border-line text-ink-dim hover:bg-paper"} disabled:opacity-40`}
                      >
                        {selectedForQuestion ? <Check size={13} /> : <BookOpen size={13} />}{selectedForQuestion ? "已加入 Local 问答" : "加入 Local 问答"}
                      </button>
                      <button type="button" onClick={() => { setPreviewNode(null); setIndexNode(selectedNode); }} className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim hover:bg-paper"><ListTree size={13} />查看文档目录与 segments</button>
                      <button type="button" onClick={() => { setIndexNode(null); setPreviewNode(selectedNode); }} className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-[12px] text-paper"><ExternalLink size={13} />预览原件</button>
                      {selectedDocument.index_job && ["queued", "running", "failed", "cancelled"].includes(selectedDocument.index_job.status) && (
                        <button
                          type="button"
                          disabled={controller.jobActionIds.includes(selectedDocument.index_job.job_id)}
                          onClick={() => { void (["queued", "running"].includes(selectedDocument.index_job!.status) ? controller.cancelIndexJob(selectedDocument.index_job!.job_id) : controller.retryIndexJob(selectedDocument.index_job!.job_id)); }}
                          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim hover:bg-paper disabled:opacity-40"
                        >
                          {controller.jobActionIds.includes(selectedDocument.index_job.job_id) ? <Loader2 className="animate-spin" size={13} /> : ["queued", "running"].includes(selectedDocument.index_job.status) ? <Ban size={13} /> : <RotateCcw size={13} />}
                          {["queued", "running"].includes(selectedDocument.index_job.status) ? "取消后台索引" : "重试后台索引"}
                        </button>
                      )}
                      {selectedDocument.warnings.length > 0 && <div className="rounded-lg bg-warn/5 px-2.5 py-2 text-[11px] leading-5 text-warn">{selectedDocument.warnings.join("；")}</div>}
                    </div>
                  )}
                </>}

                {controller.uploads.length > 0 && (
                  <section className="mt-5 border-t border-line pt-4" aria-label="最近上传">
                    <h3 className="mb-2 text-[11px] font-medium text-ink-dim">最近上传</h3>
                    <div className="space-y-1.5">
                      {controller.uploads.slice(0, 5).map((upload) => (
                        <div key={upload.id} className="rounded-lg bg-paper px-2.5 py-2 text-[11px]">
                          <div className="flex items-center gap-2"><span className="min-w-0 flex-1 truncate text-ink">{upload.name}</span><span className={upload.status === "error" || upload.status === "index_error" ? "text-err" : upload.status === "ready" ? "text-ok" : "text-ink-faint"}>{upload.status === "ready" ? "完成" : upload.status === "error" ? "失败" : upload.status === "index_error" ? "索引失败" : upload.status === "index_cancelled" ? "已取消" : "处理中"}</span></div>
                          {upload.error && <div className="mt-1 break-words text-err">{upload.error}</div>}
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </aside>
            </div>

            {previewNode && (
              <div className="absolute inset-0 z-20 flex flex-col bg-paper">
                <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                  <button type="button" onClick={() => setPreviewNode(null)} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ArrowLeft size={14} />返回知识库谱</button>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">{previewNode.label}</span>
                  <a href={originalUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ExternalLink size={13} />打开原件</a>
                </div>
                {previewNode.document_kind && ["png", "jpg", "jpeg", "webp", "tif", "tiff", "image"].includes(previewNode.document_kind.toLowerCase()) ? (
                  <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-surface p-4">
                    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated local source URL is not an optimizable asset. */}
                    <img src={originalUrl} alt={`${previewNode.label} 原件`} className="max-h-full max-w-full object-contain" />
                  </div>
                ) : (
                  <iframe src={previewUrl} title={`${previewNode.label} 原件预览`} className="min-h-0 flex-1 bg-white" />
                )}
              </div>
            )}

            {indexNode?.document_id && (
              <div className="absolute inset-0 z-20 flex flex-col bg-paper">
                <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                  <button type="button" onClick={() => setIndexNode(null)} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ArrowLeft size={14} />返回知识库谱</button>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">{indexNode.label} · 目录与 segments</span>
                  <button type="button" onClick={() => { setPreviewNode(indexNode); setIndexNode(null); }} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ExternalLink size={13} />预览原件</button>
                </div>
                <DocumentIndexView libraryId={libraryId} documentId={indexNode.document_id} />
              </div>
            )}
          </div>
        )}
        {mutation && <KnowledgeMutationDialog
          title={`${mutation.deleting ? "删除" : mutation.id ? "编辑" : "新建"}${mutation.kind === "library" ? "资料库" : mutation.kind === "topic" ? "主题" : mutation.deleting ? "文档" : "文档名称"}`}
          name={mutation.name} summary={mutation.summary} deleting={mutation.deleting}
          description={mutation.deleting
            ? mutation.kind === "topic" ? `删除「${mutation.name}」及其主题关联，文档仍保留在资料库中。`
              : mutation.kind === "library" ? `删除「${mutation.name}」及库内全部文档、原件和索引。后台任务会取消，历史引用将无法打开。此操作不可撤销。`
                : `删除「${mutation.name}」的原件、索引及全部主题关联。后台索引会取消，历史引用将无法打开。此操作不可撤销。`
            : mutation.kind === "document" ? "修改知识库中的显示名称，原文件名保持不变。" : "设置主题名称和说明，保存后可在文档详情中调整主题归属。"}
          onSave={saveMutation} onClose={() => setMutation(null)}
        />}
      </div>
    </div>
  );
}

function TopicMembershipEditor({ topics, selected, busy, onSave }: {
  topics: LocalGraphNode[]; selected: string[]; busy: boolean; onSave: (ids: string[]) => void;
}) {
  const [draft, setDraft] = useState(selected);
  const changed = [...draft].sort().join("|") !== [...selected].sort().join("|");
  return <fieldset className="space-y-2 rounded-lg border border-line p-3" disabled={busy}>
    <legend className="px-1 text-xs text-ink">主题归属</legend>
    <p className="text-[11px] text-ink-faint">最多选择三个主题；取消原主题并选择新主题即可移动。</p>
    {topics.map((topic) => <label key={topic.id} className="flex items-center gap-2 text-xs text-ink-dim">
      <input type="checkbox" checked={draft.includes(topic.subindex_id!)}
        disabled={busy || (!draft.includes(topic.subindex_id!) && draft.length >= 3)}
        onChange={(event) => setDraft(event.target.checked ? [...draft, topic.subindex_id!] : draft.filter((id) => id !== topic.subindex_id))} />
      {topic.label}
    </label>)}
    <button type="button" disabled={busy || !changed} onClick={() => onSave(draft)}
      className="rounded-md bg-clay px-3 py-1.5 text-xs text-accent-ink disabled:opacity-50">{busy ? "保存中…" : "保存主题归属"}</button>
  </fieldset>;
}
