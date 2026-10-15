import type { SourceSelection } from "./types";
import type { Turn } from "./conversation";

/** 重试和历史恢复使用该轮来源，不读取输入框中后来修改的选择。 */
export function sourceSelectionForTurn(
  turn: Pick<Turn, "sources" | "searchState" | "sourceMode">,
): SourceSelection {
  if (turn.sources) return structuredClone(turn.sources);
  const scope = turn.searchState?.source_scope;
  const mode = scope?.mode ?? turn.sourceMode ?? "web";
  if (mode === "web" || !scope?.library_id) return { mode };
  const documentIds = scope.document_ids ?? scope.documents?.map((document) => document.document_id) ?? [];
  const selection = scope.selection ?? (documentIds.length ? "documents" : "library");
  return {
    mode,
    local: {
      library_id: scope.library_id,
      selection,
      document_ids: selection === "documents" ? [...documentIds] : [],
      model_access: true,
    },
  };
}

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
