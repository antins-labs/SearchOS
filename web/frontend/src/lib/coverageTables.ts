import type { CoverageMap, TableSchema } from "@/lib/types";

/** Return every declared user schema, including schemas with no rows or cells yet. */
export function declaredCoverageTables(
  coverageMap: Pick<CoverageMap, "tables"> | null | undefined,
): TableSchema[] {
  const tables = Object.values(coverageMap?.tables ?? {});
  return tables.filter((table) => !table.table_id.startsWith("_"));
}
