/** Decode read_table pagination cursors for human-readable UI. */

const CURSOR_KEYS = new Set(["cursor", "next_cursor"]);

type CursorQuery = [unknown, unknown, unknown, unknown, unknown];

export type DecodedTableCursor = {
  version: unknown;
  after: unknown;
  table_id: unknown;
  status: unknown;
  row: unknown;
  attribute: unknown;
  unassigned_only: unknown;
};

function padBase64(value: string): string {
  const rem = value.length % 4;
  return rem ? value + "=".repeat(4 - rem) : value;
}

/** Decode a read_table cursor string. Returns null when not a table cursor. */
export function decodeTableCursor(value: string): DecodedTableCursor | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length < 8) return null;
  try {
    const raw = atob(padBase64(trimmed.replace(/-/g, "+").replace(/_/g, "/")));
    const decoded = JSON.parse(raw) as {
      version?: unknown;
      query?: unknown;
      after?: unknown;
    };
    if (!Array.isArray(decoded.query) || decoded.query.length < 5) return null;
    if (typeof decoded.after !== "string") return null;
    const [table_id, status, row, attribute, unassigned_only] = decoded.query as CursorQuery;
    return {
      version: decoded.version,
      after: decoded.after,
      table_id,
      status,
      row,
      attribute,
      unassigned_only,
    };
  } catch {
    return null;
  }
}

function rewriteCursorFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(rewriteCursorFields);
  if (!value || typeof value !== "object") return value;
  const out: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (CURSOR_KEYS.has(key) && typeof child === "string" && child) {
      const decoded = decodeTableCursor(child);
      out[key] = decoded
        ? { decoded, raw: child.length > 48 ? `${child.slice(0, 48)}…` : child }
        : child;
      continue;
    }
    out[key] = rewriteCursorFields(child);
  }
  return out;
}

/** Pretty-print tool JSON, expanding read_table cursor fields when present. */
export function prettyToolPayload(value: string): string {
  if (!value.trim()) return "No data recorded";
  try {
    const parsed = JSON.parse(value) as unknown;
    return JSON.stringify(rewriteCursorFields(parsed), null, 2);
  } catch {
    return value;
  }
}
