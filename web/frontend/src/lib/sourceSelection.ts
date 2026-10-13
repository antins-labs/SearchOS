import type { SourceSelection } from "./types";

/** 显式传递当前库或文档范围；Web 请求不携带本地授权。 */
export function buildSourceSelection(
  mode: SourceSelection["mode"], libraryId: string | null, documentIds: string[],
): SourceSelection | undefined {
  if (mode === "web") return { mode };
  if (!libraryId) return mode === "hybrid" ? { mode } : undefined;
  return {
    mode,
    local: {
      library_id: libraryId,
      selection: documentIds.length ? "documents" : "library",
      document_ids: documentIds,
      model_access: true,
    },
  };
}
