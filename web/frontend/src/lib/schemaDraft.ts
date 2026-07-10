export type TableDraft = {
  id: string;
  entityName: string;
  primaryKey: string;
  rows: string[];
  columns: string[];
};

export type RelationDraft = {
  id: string;
  fromDraftId: string;
  fromColumn: string;
  toDraftId: string;
  kind: "one_to_many" | "many_to_many";
  label: string;
};

export type SchemaSnapshot = {
  tableDrafts: TableDraft[];
  relationDrafts: RelationDraft[];
};

export type ValidationIssue = {
  key: string;
  message: string;
};

export type SchemaValidation = {
  valid: boolean;
  issues: ValidationIssue[];
  byKey: Record<string, string[]>;
};

export type ParsedDelimitedTable = {
  delimiter: "," | "\t";
  headers: string[];
  rows: string[][];
};

export type DelimitedParseResult =
  | { ok: true; table: ParsedDelimitedTable }
  | { ok: false; error: string };

const normalized = (value: string) => value.trim().toLocaleLowerCase();

const duplicateIndexes = (values: string[]) => {
  const indexes = new Map<string, number[]>();
  values.forEach((value, index) => {
    const key = normalized(value);
    if (!key) return;
    indexes.set(key, [...(indexes.get(key) ?? []), index]);
  });
  return [...indexes.values()].filter((matches) => matches.length > 1).flat();
};

export function validateSchemaDrafts(tableDrafts: TableDraft[], relationDrafts: RelationDraft[]): SchemaValidation {
  const issues: ValidationIssue[] = [];
  const add = (key: string, message: string) => issues.push({ key, message });

  tableDrafts.forEach((draft) => {
    if (!draft.entityName.trim()) add(`table:${draft.id}:entity`, "Entity name is required");
    if (!draft.primaryKey.trim()) add(`table:${draft.id}:primary`, "Primary key name is required");

    draft.columns.forEach((column, index) => {
      if (!column.trim()) add(`table:${draft.id}:column:${index}`, "Column name is required");
    });

    const allColumns = [draft.primaryKey, ...draft.columns];
    duplicateIndexes(allColumns).forEach((index) => {
      const key = index === 0
        ? `table:${draft.id}:primary`
        : `table:${draft.id}:column:${index - 1}`;
      add(key, `Duplicate column name: ${allColumns[index].trim()}`);
    });

    duplicateIndexes(draft.rows).forEach((index) => {
      add(`table:${draft.id}:row:${index}`, `Duplicate primary key value: ${draft.rows[index].trim()}`);
    });
  });

  const entityGroups = new Map<string, TableDraft[]>();
  tableDrafts.forEach((draft) => {
    const key = normalized(draft.entityName);
    if (key) entityGroups.set(key, [...(entityGroups.get(key) ?? []), draft]);
  });
  entityGroups.forEach((drafts) => {
    if (drafts.length < 2) return;
    drafts.forEach((draft) => add(`table:${draft.id}:entity`, `Duplicate entity name: ${draft.entityName.trim()}`));
  });

  const tablesById = new Map(tableDrafts.map((draft) => [draft.id, draft]));
  const relationGroups = new Map<string, RelationDraft[]>();
  relationDrafts.forEach((relation) => {
    const from = tablesById.get(relation.fromDraftId);
    const to = tablesById.get(relation.toDraftId);
    const relationKey = `relation:${relation.id}`;

    if (!from || !to) {
      add(relationKey, "Relation references a table that no longer exists");
      return;
    }
    if (from.id === to.id) add(relationKey, "Self-relations are not supported here");
    const sourceColumns = [from.primaryKey, ...from.columns].map(normalized);
    if (!relation.fromColumn.trim() || !sourceColumns.includes(normalized(relation.fromColumn))) {
      add(relationKey, "Foreign key column must exist in the source table");
    }

    const signature = [relation.fromDraftId, normalized(relation.fromColumn), relation.toDraftId].join("|");
    relationGroups.set(signature, [...(relationGroups.get(signature) ?? []), relation]);
  });
  relationGroups.forEach((relations) => {
    if (relations.length < 2) return;
    relations.forEach((relation) => add(`relation:${relation.id}`, "Duplicate relation"));
  });

  const byKey = issues.reduce<Record<string, string[]>>((result, issue) => {
    result[issue.key] = [...(result[issue.key] ?? []), issue.message];
    return result;
  }, {});
  return { valid: issues.length === 0, issues, byKey };
}

function delimiterCount(line: string, delimiter: "," | "\t") {
  let count = 0;
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    if (line[index] === '"') {
      if (quoted && line[index + 1] === '"') index += 1;
      else quoted = !quoted;
    } else if (!quoted && line[index] === delimiter) {
      count += 1;
    }
  }
  return count;
}

function parseRows(text: string, delimiter: "," | "\t"): string[][] | null {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (!quoted && char === delimiter) {
      row.push(value.trim());
      value = "";
    } else if (!quoted && (char === "\n" || char === "\r")) {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      row.push(value.trim());
      rows.push(row);
      row = [];
      value = "";
    } else {
      value += char;
    }
  }
  if (quoted) return null;
  row.push(value.trim());
  rows.push(row);
  return rows.filter((candidate) => candidate.some((cell) => cell.trim()));
}

export function parseDelimitedTable(text: string): DelimitedParseResult {
  const source = text.trim();
  if (!source) return { ok: false, error: "Paste CSV or TSV data first" };

  const firstLine = source.split(/\r?\n/, 1)[0];
  const delimiter = delimiterCount(firstLine, "\t") > delimiterCount(firstLine, ",") ? "\t" : ",";
  const rows = parseRows(source, delimiter);
  if (!rows) return { ok: false, error: "A quoted value is not closed" };
  if (rows.length < 2) return { ok: false, error: "Include a header and at least one data row" };

  const headers = rows[0].map((header) => header.trim());
  if (headers.length < 2) return { ok: false, error: "Include a primary key and at least one data column" };
  if (headers.some((header) => !header)) return { ok: false, error: "Column names cannot be empty" };
  if (duplicateIndexes(headers).length > 0) return { ok: false, error: "Column names must be unique" };

  const width = headers.length;
  const dataRows = rows.slice(1).map((candidate) => Array.from({ length: width }, (_, index) => candidate[index]?.trim() ?? ""));
  const primaryValues = dataRows.map((candidate) => candidate[0]).filter(Boolean);
  if (primaryValues.length === 0) return { ok: false, error: "The first column needs at least one primary key value" };
  if (duplicateIndexes(primaryValues).length > 0) return { ok: false, error: "Primary key values must be unique" };

  return { ok: true, table: { delimiter, headers, rows: dataRows } };
}
