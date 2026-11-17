"use client";

import { localCopy as copy } from "@/lib/localCopy";

import "./knowledgeCards.css";
import { bytesLabel, statusLabel, documentIndexProgress, uploadStatusLabel } from "@/lib/localPresentation";

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
  loading: () => <div className="grid h-full place-items-center text-sm text-ink-faint">{copy.graph.loading}</div>,
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

function DocumentIndexProgress({ document }: { document: LocalDocument }) {
  const progress = documentIndexProgress(document);
  return (
    <div className="rounded-lg border border-line bg-paper px-2.5 py-2">
      <div className="mb-1.5 flex items-center justify-between gap-2 text-[10.5px]">
        <span className="text-ink-dim">{progress.label}</span>
        {progress.total > 0 && (
          <span className="tabular-nums text-ink-faint">
            {copy.count.segments(progress.completed, progress.total)}
          </span>
        )}
      </div>
      <div
        role="progressbar"
        aria-label={copy.document.progress}
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
            <h1 id="knowledge-base-title" className="font-semibold tracking-tight text-[19px] text-ink">{copy.library.title}</h1>
            <p className="text-[11px] text-ink-faint">{copy.library.documentsAndTopics}</p>
          </div>
          {currentLibrary && <div className="min-w-0 max-w-64 rounded-lg border border-line bg-surface-2 px-3 py-1.5"><div className="text-[9px] uppercase tracking-wider text-ink-faint">{copy.library.current}</div><div className="truncate text-[12px] font-medium text-ink">{currentLibrary.name}</div></div>}
          <button type="button" onClick={() => setNewLibraryOpen((value) => !value)} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-[12px] text-ink-dim hover:bg-surface-2"><Plus size={13} />{copy.actions.newLibrary}</button>
          <button type="button" disabled={!libraryId} onClick={() => libraryId && setMutation({ kind: "topic", libraryId, name: "", summary: "" })}
            className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-[12px] text-ink-dim hover:bg-surface-2 disabled:opacity-40"><Plus size={13} />{copy.actions.newTopic}</button>
          <button type="button" disabled={controller.uploading} onClick={() => inputRef.current?.click()} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-[12px] text-paper hover:opacity-90 disabled:opacity-40">
            {controller.uploading ? <Loader2 className="animate-spin" size={13} /> : <FileUp size={13} />}{copy.actions.addDocument}
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
          <button type="button" onClick={() => { setGraphRefresh((value) => value + 1); void controller.refreshDocuments(); }} disabled={!libraryId || controller.loading} className="ml-auto rounded-lg p-2 text-ink-dim hover:bg-surface-2 disabled:opacity-40" aria-label={copy.actions.refresh}><RefreshCw className={controller.loading ? "animate-spin" : ""} size={15} /></button>
          <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-2 text-ink-dim hover:bg-surface-2" aria-label={copy.actions.closeLibrary}><X size={17} /></button>
        </header>

        {newLibraryOpen && (
          <div className="flex items-center gap-2 border-b border-line bg-surface-2/50 px-5 py-2.5">
            <input
              autoFocus
              value={newLibraryName}
              onChange={(event) => setNewLibraryName(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void submitLibrary(); }}
              placeholder={copy.library.name}
              maxLength={120}
              className="w-full max-w-sm rounded-lg border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
            />
            <button type="button" disabled={!newLibraryName.trim() || controller.creatingLibrary} onClick={() => { void submitLibrary(); }} className="rounded-lg bg-ink px-3 py-2 text-[12px] text-paper disabled:opacity-40">
              {controller.creatingLibrary ? copy.actions.creating : copy.actions.create}
            </button>
            <button type="button" onClick={() => setNewLibraryOpen(false)} className="rounded-lg px-3 py-2 text-[12px] text-ink-faint hover:bg-surface-2">{copy.actions.cancel}</button>
          </div>
        )}

        {controller.error && <div role="alert" className="border-b border-err/30 bg-err/5 px-5 py-2 text-[12px] text-err">{controller.error}</div>}

        {!libraryId ? (
          <div className="grid min-h-0 flex-1 place-items-center p-6 text-center">
            <div>
              <Database className="mx-auto mb-3 text-ink-faint" size={30} />
              <h2 className="text-[15px] font-medium text-ink">{copy.empty.library}</h2>
              <p className="mt-1 text-[12px] text-ink-faint">{copy.empty.createLibrary}</p>
              <button type="button" onClick={() => setNewLibraryOpen(true)} className="mt-4 rounded-lg bg-ink px-4 py-2 text-[12px] text-paper">{copy.actions.newLibrary}</button>
            </div>
          </div>
        ) : (
          <div className="relative flex min-h-0 flex-1 flex-col">
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
              <label className="flex min-w-52 flex-1 items-center gap-2 rounded-xl border border-line bg-paper px-3 py-2.5 text-ink-faint focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/10 sm:max-w-md">
                <Search size={13} />
                <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label={copy.library.searchLabel} placeholder={copy.library.search} className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-ink-faint" />
                {query && <button type="button" onClick={() => setQuery("")} aria-label={copy.actions.clearSearch}><X size={12} /></button>}
              </label>
              <span className="flex items-center gap-1 text-[11px] text-ink-faint"><FolderTree size={12} />{copy.count.topics(graphCounts.topics)}</span>
              <span className="flex items-center gap-1 text-[11px] text-ink-faint"><FileText size={12} />{copy.count.documents(graphCounts.documents)}</span>
              <span className="hidden text-[11px] text-ink-faint xl:inline">{viewMode === "graph" ? copy.graph.dragHint : copy.library.browse}</span>
              <div className="flex rounded-lg border border-line bg-surface p-0.5" role="group" aria-label={copy.library.viewMode}>
                <button type="button" onClick={() => setViewMode("list")} className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] ${viewMode === "list" ? "bg-ink text-paper" : "text-ink-dim hover:bg-surface-2"}`} aria-pressed={viewMode === "list"}><List size={12} />{copy.library.listView}</button>
                <button type="button" onClick={() => setViewMode("graph")} className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] ${viewMode === "graph" ? "bg-ink text-paper" : "text-ink-dim hover:bg-surface-2"}`} aria-pressed={viewMode === "graph"}><Network size={12} />{copy.library.graphView}</button>
              </div>
            </div>

            {graphMutationError && <div role="alert" className="border-b border-err/30 bg-err/5 px-4 py-2 text-[11px] text-err">{graphMutationError}</div>}

            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:grid lg:overflow-hidden lg:grid-cols-[180px_minmax(0,1fr)_280px] xl:grid-cols-[200px_minmax(0,1fr)_310px]">
              <nav className="max-h-40 shrink-0 overflow-y-auto border-b border-line bg-surface/60 p-3 lg:max-h-none lg:border-b-0 lg:border-r" aria-label={copy.library.list}>
                <div className="mb-2 flex items-center justify-between px-1">
                  <div>
                    <h2 className="text-[12px] font-medium text-ink">{copy.library.list}</h2>
                    <p className="text-[10px] text-ink-faint">{copy.count.libraries(controller.libraries.length)}</p>
                  </div>
                  <button type="button" onClick={() => setNewLibraryOpen(true)} className="rounded-lg p-1.5 text-ink-faint hover:bg-paper hover:text-ink" aria-label={copy.actions.newLibrary}><Plus size={14} /></button>
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
                            aria-label={copy.library.newName}
                            className="w-full rounded-md border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-accent"
                          />
                          <div className="mt-1.5 flex justify-end gap-1">
                            <button type="button" onClick={() => setRenamingLibraryId(null)} className="rounded px-2 py-1 text-[10px] text-ink-faint hover:bg-surface-2">{copy.actions.cancel}</button>
                            <button type="button" disabled={!renameValue.trim() || controller.renamingLibraryId === library.library_id} onClick={() => { void submitRename(); }} className="rounded bg-ink px-2 py-1 text-[10px] text-paper disabled:opacity-40">{controller.renamingLibraryId === library.library_id ? copy.actions.saving : copy.actions.save}</button>
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
                            <span className="block truncate text-[10px] text-ink-faint">{active ? copy.library.current : copy.actions.open}</span>
                          </span>
                        </button>
                        <button type="button" onClick={() => beginRename(library.library_id, library.name)} className="mr-1 rounded-md p-1.5 text-ink-faint opacity-60 hover:bg-surface-2 hover:text-ink group-hover:opacity-100" aria-label={copy.rename(library.name)}><Pencil size={12} /></button>
                        <button type="button" disabled={controller.uploading} onClick={() => setMutation({ kind: "library", libraryId: library.library_id, name: library.name, deleting: true })}
                          className="mr-1 rounded-md p-1.5 text-ink-faint hover:bg-err/10 hover:text-err disabled:opacity-40" aria-label={copy.remove(library.name)}><Trash2 size={12} /></button>
                      </div>
                    );
                  })}
                </div>
              </nav>
              <section className="h-[60dvh] min-h-[28rem] shrink-0 overflow-hidden border-b border-line lg:h-auto lg:min-h-0 lg:border-b-0 lg:border-r" aria-label={viewMode === "graph" ? copy.library.graph : copy.library.documentList}>
                {!graph && !graphError && <div className="grid h-full place-items-center text-[13px] text-ink-faint"><span className="flex items-center gap-2"><Loader2 className="animate-spin" size={14} />{copy.graph.loading}</span></div>}
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

              <aside className="shrink-0 bg-surface/50 p-4 lg:min-h-0 lg:overflow-y-auto" aria-label={copy.library.detail}>
                {!selectedNode ? <p className="text-[13px] text-ink-faint">{copy.library.selectItem}</p> : <>
                  <div className="mb-3 flex items-start gap-2">
                    {selectedNode.node_type === "document" ? <FileBadge kind={selectedNode.document_kind} filename={selectedNode.label} /> :
                      <span className={`mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-xl ${selectedNode.node_type === "index" ? "border border-line-strong bg-clay text-accent-ink" : "knowledge-folder-badge"}`}>
                        {selectedNode.node_type === "index" ? <LibraryBig size={23} strokeWidth={1.5} /> : <FolderOpen size={21} strokeWidth={1.5} />}
                      </span>}
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-wider text-ink-faint">{selectedNode.node_type === "index" ? copy.library.root : selectedNode.node_type === "subindex" ? copy.library.topic : copy.document.title}</div>
                      <h2 className="break-words text-[14px] font-medium text-ink">{selectedNode.label}</h2>
                    </div>
                  </div>
                  {selectedNode.original_name && selectedNode.original_name !== selectedNode.label && (
                    <p className="mb-2 break-all text-[11px] text-ink-faint">{copy.document.originalName}{selectedNode.original_name}</p>
                  )}
                  {selectedNode.node_type === "subindex" && selectedNode.recap_status === "pending" && (
                    <p className="mb-2 text-xs text-ink-faint" role="status">{copy.library.topicSummaryPending}</p>
                  )}
                  {selectedNode.node_type === "subindex" && selectedNode.recap_status === "failed" && (
                    <div className="mb-2 text-xs text-warn">
                      <p title={selectedNode.recap_error}>{copy.library.topicSummaryFailed}</p>
                      <button type="button" className="mt-1 underline" onClick={async () => {
                        try { setGraphState({ libraryId, graph: await retryLocalTopicRecaps(libraryId) }); }
                        catch (cause) { setGraphMutationError(cause instanceof Error ? cause.message : String(cause)); }
                      }}>{copy.actions.retry}</button>
                    </div>
                  )}
                  <p className="mb-4 whitespace-pre-wrap text-[12px] leading-5 text-ink-dim">{selectedNode.summary || copy.library.noSummary}</p>
                  {(selectedNode.node_type === "document" || selectedNode.node_type === "subindex") && <div className="mb-4 flex gap-2">
                    <button type="button" disabled={Boolean(mutatingDocumentId)} onClick={() => setMutation({
                      kind: selectedNode.node_type === "document" ? "document" : "topic", libraryId,
                      id: selectedNode.document_id ?? selectedNode.subindex_id, name: selectedNode.label,
                      summary: selectedNode.node_type === "subindex" ? selectedNode.summary : undefined,
                    })} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line px-2 py-2 text-xs text-ink-dim hover:bg-paper disabled:opacity-40"><Pencil size={12} />{copy.actions.edit}{selectedNode.node_type === "document" ? copy.document.name : copy.library.topic}</button>
                    <button type="button" disabled={Boolean(mutatingDocumentId)} onClick={() => setMutation({
                      kind: selectedNode.node_type === "document" ? "document" : "topic", libraryId,
                      id: selectedNode.document_id ?? selectedNode.subindex_id, name: selectedNode.label, deleting: true,
                    })} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-err hover:bg-err/10 disabled:opacity-40"><Trash2 size={12} />{copy.actions.delete}</button>
                  </div>}

                  {selectedNode.node_type === "index" && (
                    <div className="space-y-2 text-[12px] text-ink-dim">
                      <div className="flex justify-between border-b border-line pb-2"><span>{copy.library.topic}</span><span>{graphCounts.topics}</span></div>
                      <div className="flex justify-between border-b border-line pb-2"><span>{copy.document.title}</span><span>{graphCounts.documents}</span></div>
                      <div className="pt-2 text-[11px] leading-5 text-ink-faint">{copy.graph.pendingHint}</div>
                    </div>
                  )}

                  {selectedNode.node_type === "subindex" && (
                    <div className="space-y-2 text-[12px] text-ink-dim">
                      <div className="flex justify-between border-b border-line pb-2"><span>{copy.document.linkedDocuments}</span><span>{selectedNode.document_count ?? 0}</span></div>
                      <div className="flex justify-between border-b border-line pb-2"><span>{copy.document.characterCount}</span><span>{selectedNode.character_count?.toLocaleString() ?? 0}</span></div>
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
                        {[[copy.document.parse, selectedDocument.parse_status], [copy.document.recap, selectedDocument.recap_status], [copy.document.catalog, selectedDocument.catalog_status]].map(([label, status]) => (
                          <div key={label} className="rounded-lg bg-paper px-1.5 py-2"><div className="text-ink-faint">{label}</div><div className={status === "failed" ? "mt-0.5 text-err" : status === "ready" ? "mt-0.5 text-ok" : "mt-0.5 text-warn"}>{statusLabel(status)}</div></div>
                        ))}
                      </div>
                      <div className="space-y-1 text-[11px] text-ink-faint">
                        <div className="flex justify-between"><span>{copy.document.format}</span><span>{selectedDocument.kind.toUpperCase()}</span></div>
                        <div className="flex justify-between"><span>{copy.document.size}</span><span>{bytesLabel(selectedDocument.size_bytes)}</span></div>
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
                        {selectedForQuestion ? <Check size={13} /> : <BookOpen size={13} />}{selectedForQuestion ? copy.actions.included : copy.actions.include}
                      </button>
                      <button type="button" onClick={() => { setPreviewNode(null); setIndexNode(selectedNode); }} className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim hover:bg-paper"><ListTree size={13} />{copy.actions.viewOutline}</button>
                      <button type="button" onClick={() => { setIndexNode(null); setPreviewNode(selectedNode); }} className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-[12px] text-paper"><ExternalLink size={13} />{copy.actions.preview}</button>
                      {selectedDocument.index_job && ["queued", "running", "failed", "cancelled"].includes(selectedDocument.index_job.status) && (
                        <button
                          type="button"
                          disabled={controller.jobActionIds.includes(selectedDocument.index_job.job_id)}
                          onClick={() => { void (["queued", "running"].includes(selectedDocument.index_job!.status) ? controller.cancelIndexJob(selectedDocument.index_job!.job_id) : controller.retryIndexJob(selectedDocument.index_job!.job_id)); }}
                          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[12px] text-ink-dim hover:bg-paper disabled:opacity-40"
                        >
                          {controller.jobActionIds.includes(selectedDocument.index_job.job_id) ? <Loader2 className="animate-spin" size={13} /> : ["queued", "running"].includes(selectedDocument.index_job.status) ? <Ban size={13} /> : <RotateCcw size={13} />}
                          {["queued", "running"].includes(selectedDocument.index_job.status) ? copy.actions.cancelIndex : copy.actions.retryIndex}
                        </button>
                      )}
                      {selectedDocument.warnings.length > 0 && <details className="rounded-lg bg-warn/5 px-2.5 py-2 text-[11px] leading-5 text-warn"><summary className="cursor-pointer">{copy.document.processingNotes}</summary><ul className="mt-1 list-inside list-disc">{selectedDocument.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
                    </div>
                  )}
                </>}

                {controller.uploads.length > 0 && (
                  <section className="mt-5 border-t border-line pt-4" aria-label={copy.library.recentUploads}>
                    <h3 className="mb-2 text-[11px] font-medium text-ink-dim">{copy.library.recentUploads}</h3>
                    <div className="space-y-1.5">
                      {controller.uploads.slice(0, 5).map((upload) => (
                        <div key={upload.id} className="rounded-lg bg-paper px-2.5 py-2 text-[11px]">
                          <div className="flex items-center gap-2"><span className="min-w-0 flex-1 truncate text-ink">{upload.name}</span><span className={upload.status === "error" || upload.status === "index_error" ? "text-err" : upload.status === "ready" ? "text-ok" : "text-ink-faint"}>{uploadStatusLabel(upload)}</span></div>
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
                  <button type="button" onClick={() => setPreviewNode(null)} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ArrowLeft size={14} />{copy.actions.back}</button>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">{previewNode.label}</span>
                  <a href={originalUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ExternalLink size={13} />{copy.actions.openOriginal}</a>
                </div>
                {previewNode.document_kind && ["png", "jpg", "jpeg", "webp", "tif", "tiff", "image"].includes(previewNode.document_kind.toLowerCase()) ? (
                  <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-surface p-4">
                    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated local source URL is not an optimizable asset. */}
                    <img src={originalUrl} alt={copy.original(previewNode.label)} className="max-h-full max-w-full object-contain" />
                  </div>
                ) : (
                  <iframe src={previewUrl} title={copy.original(previewNode.label)} className="min-h-0 flex-1 bg-white" />
                )}
              </div>
            )}

            {indexNode?.document_id && (
              <div className="absolute inset-0 z-20 flex flex-col bg-paper">
                <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                  <button type="button" onClick={() => setIndexNode(null)} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ArrowLeft size={14} />{copy.actions.back}</button>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">{indexNode.label} · {copy.document.outline}</span>
                  <button type="button" onClick={() => { setPreviewNode(indexNode); setIndexNode(null); }} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink-dim hover:bg-surface-2"><ExternalLink size={13} />{copy.actions.preview}</button>
                </div>
                <DocumentIndexView libraryId={libraryId} documentId={indexNode.document_id} />
              </div>
            )}
          </div>
        )}
        {mutation && <KnowledgeMutationDialog
          title={copy.mutationTitle(mutation.kind, Boolean(mutation.deleting), Boolean(mutation.id))}
          name={mutation.name} summary={mutation.summary} deleting={mutation.deleting}
          description={mutation.deleting
            ? mutation.kind === "topic" ? copy.deleteTopic(mutation.name)
              : mutation.kind === "library" ? copy.deleteLibrary(mutation.name)
                : copy.deleteDocument(mutation.name)
            : mutation.kind === "document" ? copy.editDocument : copy.editTopic}
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
    <legend className="px-1 text-xs text-ink">{copy.library.topicMembership}</legend>
    <p className="text-[11px] text-ink-faint">{copy.library.topicLimit}</p>
    {topics.map((topic) => <label key={topic.id} className="flex items-center gap-2 text-xs text-ink-dim">
      <input type="checkbox" checked={draft.includes(topic.subindex_id!)}
        disabled={busy || (!draft.includes(topic.subindex_id!) && draft.length >= 3)}
        onChange={(event) => setDraft(event.target.checked ? [...draft, topic.subindex_id!] : draft.filter((id) => id !== topic.subindex_id))} />
      {topic.label}
    </label>)}
    <button type="button" disabled={busy || !changed} onClick={() => onSave(draft)}
      className="rounded-md bg-clay px-3 py-1.5 text-xs text-accent-ink disabled:opacity-50">{busy ? copy.actions.saving : copy.actions.save}</button>
  </fieldset>;
}
