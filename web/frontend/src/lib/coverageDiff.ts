import type { CoverageCell, CoverageMap } from "./types";
import { cellRef, rowKey } from "./socmRefs";

export type CoverageDiffKind = "added" | "modified" | "removed" | "conflict_resolved";

export interface CoverageCellDiff {
  key: string;
  kind: CoverageDiffKind;
  tableId: string;
  tableLabel: string;
  entity: string;
  attribute: string;
  before?: CoverageCell;
  after?: CoverageCell;
}

const comparableCell = (cell: CoverageCell) => JSON.stringify({
  value: cell.value,
  status: cell.status,
  source: cell.source,
  confidence: cell.confidence,
  supportingEvidenceIds: [...(cell.supporting_evidence_ids ?? [])].sort(),
  primaryEvidenceId: cell.primary_evidence_id,
  hasConflict: !!cell.has_conflict,
  conflictEvidenceIds: [...(cell.conflict_evidence_ids ?? [])].sort(),
});

function cellIdentity(key: string, maps: CoverageMap[]): Omit<CoverageCellDiff, "key" | "kind" | "before" | "after"> {
  const ref = cellRef(key);
  const tableId = ref.table_id;
  const schema = maps.map((map) => map.tables[tableId]).find(Boolean);
  const entity = rowKey(ref.key);

  return {
    tableId,
    tableLabel: schema?.table_label || tableId,
    entity,
    attribute: ref.attribute,
  };
}

export function diffCoverageMaps(before: CoverageMap, after: CoverageMap): CoverageCellDiff[] {
  const keys = new Set([...Object.keys(before.cells ?? {}), ...Object.keys(after.cells ?? {})]);
  const changes: CoverageCellDiff[] = [];

  for (const key of [...keys].sort()) {
    if (key.startsWith("_")) continue;
    const previous = before.cells[key];
    const current = after.cells[key];
    const identity = cellIdentity(key, [after, before]);

    if (!previous && current) {
      changes.push({ key, kind: "added", ...identity, after: current });
    } else if (previous && !current) {
      changes.push({ key, kind: "removed", ...identity, before: previous });
    } else if (previous && current && previous.has_conflict && !current.has_conflict) {
      changes.push({ key, kind: "conflict_resolved", ...identity, before: previous, after: current });
    } else if (previous && current && comparableCell(previous) !== comparableCell(current)) {
      changes.push({ key, kind: "modified", ...identity, before: previous, after: current });
    }
  }

  return changes;
}

export function coverageDiffCounts(changes: CoverageCellDiff[]) {
  return changes.reduce((counts, change) => {
    counts[change.kind] += 1;
    return counts;
  }, { added: 0, modified: 0, removed: 0, conflict_resolved: 0 });
}
