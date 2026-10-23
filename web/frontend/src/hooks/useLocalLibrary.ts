"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  cancelLocalIndexJob,
  createLocalLibrary,
  deleteLocalLibrary,
  deleteLocalDocument,
  listLocalDocuments,
  listLocalLibraries,
  renameLocalLibrary,
  retryLocalIndexJob,
  uploadLocalDocument,
} from "@/lib/api";
import { buildSourceSelection } from "@/lib/sourceSelection";
import type { LocalDocument, LocalLibrary, LocalLibraryGraph, SourceSelection } from "@/lib/types";

export interface LocalUploadItem {
  id: string;
  name: string;
  sizeBytes: number;
  progress: number;
  documentId?: string;
  status: "queued" | "uploading" | "parsing" | "indexing" | "ready" | "index_error" | "index_cancelled" | "error";
  error?: string;
  cached?: boolean;
}

export interface LocalLibraryController {
  mode: "web" | "local" | "hybrid";
  setMode: (mode: "web" | "local" | "hybrid") => void;
  libraries: LocalLibrary[];
  libraryId: string | null;
  setLibraryId: (libraryId: string) => void;
  documents: LocalDocument[];
  selectedDocumentIds: string[];
  setDocumentSelected: (documentId: string, selected: boolean) => void;
  uploads: LocalUploadItem[];
  loading: boolean;
  uploading: boolean;
  creatingLibrary: boolean;
  renamingLibraryId: string | null;
  error: string | null;
  createLibrary: (name: string) => Promise<void>;
  renameLibrary: (libraryId: string, name: string) => Promise<void>;
  deleteLibrary: (libraryId: string) => Promise<void>;
  deleteDocument: (libraryId: string, documentId: string) => Promise<LocalLibraryGraph>;
  refreshDocuments: () => Promise<void>;
  uploadFiles: (files: File[]) => Promise<void>;
  jobActionIds: string[];
  cancelIndexJob: (jobId: string) => Promise<void>;
  retryIndexJob: (jobId: string) => Promise<void>;
  selection: SourceSelection | undefined;
  restoreSelection: (selection: SourceSelection) => void;
}

export function useLocalLibrary(): LocalLibraryController {
  const [mode, setMode] = useState<"web" | "local" | "hybrid">("web");
  const [libraries, setLibraries] = useState<LocalLibrary[]>([]);
  const [libraryId, setLibraryIdState] = useState<string | null>(null);
  const currentLibraryId = useRef<string | null>(null);
  const documentsRevision = useRef(0);
  const updateLibraryId = useCallback((next: string | null) => {
    if (currentLibraryId.current === next) return;
    currentLibraryId.current = next;
    documentsRevision.current += 1;
    setLibraryIdState(next);
    setDocuments([]);
    setSelectedDocumentIds([]);
    setUploads([]);
  }, []);
  const [documents, setDocuments] = useState<LocalDocument[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [uploads, setUploads] = useState<LocalUploadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingLibrary, setCreatingLibrary] = useState(false);
  const [renamingLibraryId, setRenamingLibraryId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobActionIds, setJobActionIds] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    void listLocalLibraries()
      .then((items) => {
        if (!alive) return;
        setLibraries(items);
        if (!currentLibraryId.current) updateLibraryId(items[0]?.library_id ?? null);
        setError(null);
      })
      .catch((cause) => { if (alive) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [updateLibraryId]);

  const applyDocuments = useCallback((items: LocalDocument[]) => {
    setDocuments(items);
    const available = new Set(items.filter((item) => item.searchable).map((item) => item.document_id));
    setSelectedDocumentIds((current) => current.filter((id) => available.has(id)));
    setUploads((current) => current.map((upload) => {
      if (!upload.documentId) return upload;
      const document = items.find((item) => item.document_id === upload.documentId);
      const job = document?.index_job;
      if (!job) return upload;
      if (job.status === "completed") return { ...upload, status: "ready", error: undefined };
      if (job.status === "failed") return { ...upload, status: "index_error", error: job.error || "资料处理失败" };
      if (job.status === "cancelled") return { ...upload, status: "index_cancelled", error: undefined };
      return { ...upload, status: "indexing", error: undefined };
    }));
  }, []);

  useEffect(() => {
    if (!libraryId) return;
    let alive = true;
    const revision = documentsRevision.current;
    void listLocalDocuments(libraryId)
      .then((items) => {
        if (!alive || revision !== documentsRevision.current || currentLibraryId.current !== libraryId) return;
        applyDocuments(items);
        setError(null);
      })
      .catch((cause) => { if (alive) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [applyDocuments, libraryId]);

  useEffect(() => {
    if (!libraryId || !documents.some((document) => (
      document.index_job?.status === "queued" || document.index_job?.status === "running"
    ))) return;
    let alive = true;
    const refresh = () => {
      const revision = documentsRevision.current;
      void listLocalDocuments(libraryId)
        .then((items) => {
          if (!alive || revision !== documentsRevision.current || currentLibraryId.current !== libraryId) return;
          applyDocuments(items);
          setError(null);
        })
        .catch((cause) => {
          if (alive) setError(cause instanceof Error ? cause.message : String(cause));
        });
    };
    const timer = window.setInterval(refresh, 1500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [applyDocuments, documents, libraryId]);

  const setLibraryId = useCallback((next: string) => {
    if (currentLibraryId.current === next) return;
    setLoading(true);
    updateLibraryId(next);
  }, [updateLibraryId]);

  const restoreSelection = useCallback((selection: SourceSelection) => {
    setMode(selection.mode);
    if (selection.local) {
      updateLibraryId(selection.local.library_id);
    }
    setSelectedDocumentIds(selection.local?.document_ids ?? []);
  }, [updateLibraryId]);

  const setDocumentSelected = useCallback((documentId: string, selected: boolean) => {
    setSelectedDocumentIds((current) => selected
      ? Array.from(new Set([...current, documentId]))
      : current.filter((id) => id !== documentId));
  }, []);

  const refreshDocuments = useCallback(async () => {
    if (!libraryId) {
      setDocuments([]);
      return;
    }
    setLoading(true);
    setError(null);
    const revision = documentsRevision.current;
    try {
      const items = await listLocalDocuments(libraryId);
      if (revision === documentsRevision.current && currentLibraryId.current === libraryId) applyDocuments(items);
    } catch (cause) {
      if (currentLibraryId.current === libraryId && revision === documentsRevision.current) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    } finally {
      if (currentLibraryId.current === libraryId) setLoading(false);
    }
  }, [applyDocuments, libraryId]);

  const createLibrary = useCallback(async (name: string) => {
    const cleaned = name.trim();
    if (!cleaned) return;
    setCreatingLibrary(true);
    setError(null);
    try {
      const created = await createLocalLibrary(cleaned);
      setLibraries((current) => [...current, created]);
      updateLibraryId(created.library_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setCreatingLibrary(false);
    }
  }, [updateLibraryId]);

  const renameLibrary = useCallback(async (targetLibraryId: string, name: string) => {
    const cleaned = name.trim();
    if (!cleaned) return;
    setRenamingLibraryId(targetLibraryId);
    setError(null);
    try {
      const renamed = await renameLocalLibrary(targetLibraryId, cleaned);
      setLibraries((current) => current.map((library) => (
        library.library_id === renamed.library_id ? renamed : library
      )));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    } finally {
      setRenamingLibraryId(null);
    }
  }, []);

  const deleteLibrary = useCallback(async (targetLibraryId: string) => {
    await deleteLocalLibrary(targetLibraryId);
    setLibraries((current) => current.filter((item) => item.library_id !== targetLibraryId));
    if (currentLibraryId.current === targetLibraryId) {
      updateLibraryId(libraries.find((item) => item.library_id !== targetLibraryId)?.library_id ?? null);
      setLoading(false);
    }
    setError(null);
  }, [libraries, updateLibraryId]);

  const deleteDocument = useCallback(async (targetLibraryId: string, documentId: string) => {
    const graph = await deleteLocalDocument(targetLibraryId, documentId);
    if (currentLibraryId.current === targetLibraryId) {
      documentsRevision.current += 1;
      setDocuments((current) => current.filter((item) => item.document_id !== documentId));
      setSelectedDocumentIds((current) => current.filter((id) => id !== documentId));
      setUploads((current) => current.filter((item) => item.documentId !== documentId));
    }
    return graph;
  }, []);

  const runJobAction = useCallback(async (jobId: string, action: "cancel" | "retry") => {
    if (!libraryId) return;
    const revision = documentsRevision.current;
    setJobActionIds((current) => Array.from(new Set([...current, jobId])));
    setError(null);
    try {
      if (action === "cancel") await cancelLocalIndexJob(libraryId, jobId);
      else await retryLocalIndexJob(libraryId, jobId);
      const items = await listLocalDocuments(libraryId);
      if (currentLibraryId.current === libraryId && revision === documentsRevision.current) applyDocuments(items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setJobActionIds((current) => current.filter((id) => id !== jobId));
    }
  }, [applyDocuments, libraryId]);

  const cancelIndexJob = useCallback(
    (jobId: string) => runJobAction(jobId, "cancel"),
    [runJobAction],
  );
  const retryIndexJob = useCallback(
    (jobId: string) => runJobAction(jobId, "retry"),
    [runJobAction],
  );

  const uploadFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setMode((current) => current === "hybrid" ? "hybrid" : "local");
    setError(null);
    let targetLibraryId = libraryId;
    if (!targetLibraryId) {
      const created = await createLocalLibrary();
      setLibraries((current) => [...current, created]);
      updateLibraryId(created.library_id);
      targetLibraryId = created.library_id;
    }
    const items = files.map((file, index) => ({
      id: `${Date.now()}_${index}_${file.name}`,
      name: file.name,
      sizeBytes: file.size,
      progress: 0,
      status: "queued" as const,
    }));
    setUploads((current) => [...items, ...current].slice(0, 12));
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const item = items[index];
      try {
        setUploads((current) => current.map((upload) => upload.id === item.id
          ? { ...upload, status: "uploading" }
          : upload));
        const document = await uploadLocalDocument(targetLibraryId, file, (progress) => {
          setUploads((current) => current.map((upload) => upload.id === item.id
            ? {
                ...upload,
                progress: progress.percent,
                status: progress.phase,
              }
            : upload));
        });
        if (currentLibraryId.current !== targetLibraryId) continue;
        setDocuments((current) => [document, ...current.filter((existing) => existing.document_id !== document.document_id)]);
        if (document.searchable) {
          setSelectedDocumentIds((current) => Array.from(new Set([...current, document.document_id])));
        }
        setUploads((current) => current.map((upload) => upload.id === item.id
          ? {
              ...upload,
              documentId: document.document_id,
              progress: 100,
              status: document.index_job?.status === "completed" ? "ready" : document.index_job?.status === "failed" ? "index_error" : document.index_job?.status === "cancelled" ? "index_cancelled" : "indexing",
              error: document.index_job?.status === "failed" ? document.index_job.error : undefined,
              cached: document.cached,
            }
          : upload));
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        setUploads((current) => current.map((upload) => upload.id === item.id
          ? { ...upload, status: "error", error: message }
          : upload));
        setError(message);
      }
    }
  }, [libraryId, updateLibraryId]);

  const uploading = uploads.some((item) => ["queued", "uploading", "parsing"].includes(item.status));
  const selection = useMemo(() => buildSourceSelection(mode, libraryId, selectedDocumentIds),
    [libraryId, mode, selectedDocumentIds]);

  return {
    mode, setMode, libraries, libraryId, setLibraryId, documents,
    selectedDocumentIds, setDocumentSelected, uploads, loading, uploading,
    creatingLibrary, renamingLibraryId, error, createLibrary, renameLibrary, deleteLibrary, deleteDocument,
    refreshDocuments, uploadFiles,
    jobActionIds, cancelIndexJob, retryIndexJob, selection, restoreSelection,
  };
}
