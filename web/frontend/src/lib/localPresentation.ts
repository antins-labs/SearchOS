import type { LocalDocument, LocalUploadItem } from "./types";
import { localCopy as copy } from "./localCopy";

export function bytesLabel(bytes = 0): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

export function statusLabel(status = "pending"): string {
  if (status === "completed") return copy.status.ready;
  return copy.status[status as "ready" | "partial" | "failed" | "cancelled" | "queued" | "running" | "pending"] ?? copy.status.pending;
}

export function documentIndexProgress(document: LocalDocument) {
  const completed = document.index_job?.recap_segments_completed ?? document.recap_segments_completed;
  const total = document.index_job?.recap_segments_total ?? document.recap_segments_total;
  const job = document.index_job?.status;
  const active = job === "queued" || job === "running";
  const failed = !active && document.recap_status === "failed";
  const labels = {
    ready: copy.status.recapReady, partial: copy.status.recapPartial,
    failed: copy.status.recapFailed, pending: copy.status.recapPending,
  };
  return {
    completed, total, failed,
    percent: total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0,
    indeterminate: total === 0 && active,
    label: active ? (job === "queued" ? copy.status.queued : copy.status.indexing)
      : document.recap_status === "ready" ? copy.status.recapReady
      : job === "cancelled" ? copy.status.recapCancelled : labels[document.recap_status],
  };
}

export function uploadStatusLabel(item: LocalUploadItem): string {
  const labels = {
    queued: copy.status.uploadQueued, uploading: copy.count.uploading(item.progress),
    parsing: copy.status.parsing, indexing: copy.status.indexing,
    ready: item.cached ? copy.status.cached : copy.status.completed,
    index_error: copy.status.indexFailed, index_cancelled: copy.status.cancelled,
    error: copy.status.uploadFailed,
  };
  return labels[item.status];
}

export function documentStatusLabel(document: LocalDocument): string {
  if (!document.searchable) {
    if (document.parse_status === "failed") return copy.status.parseFailed;
    return document.parse_status === "pending" ? copy.status.saved : copy.status.partial;
  }
  const job = document.index_job?.status;
  if (job === "queued" || job === "running") return copy.status.indexing;
  if (job === "failed") return copy.status.indexFailed;
  if (job === "cancelled") return copy.status.cancelled;
  return document.catalog_status === "ready" ? copy.status.catalogReady : copy.status.available;
}
