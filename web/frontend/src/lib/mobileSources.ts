import type { LocalDocument, SourceSelection } from "./types";

/** A cancelled/empty mobile picker must never authorize the whole library. */
export function mobileSourceSelection(
  mode: SourceSelection["mode"], libraryId: string | null,
  documents: Pick<LocalDocument, "document_id" | "searchable">[], selectedIds: string[],
): SourceSelection | undefined {
  if (mode === "web") return { mode: "web" };
  if (!libraryId) return undefined;
  const allowed = new Set(documents.filter(doc => doc.searchable).map(doc => doc.document_id));
  const documentIds = [...new Set(selectedIds)].filter(id => allowed.has(id));
  if (!documentIds.length) return undefined;
  return { mode, local: { library_id: libraryId, document_ids: documentIds, selection: "documents", model_access: true } };
}
