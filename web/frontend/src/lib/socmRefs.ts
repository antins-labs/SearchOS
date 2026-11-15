/** SOCM v2 引用；编码须与 Python searchos.socm.refs 一致。 */
export interface RowRef { table_id: string; key: string[] }
export interface CellRef extends RowRef { attribute: string }

export function rowKey(values: string[]): string {
  if (!Array.isArray(values) || !values.length || values.some(v => typeof v !== "string" || !v.trim())) {
    throw new Error("Incomplete row key");
  }
  return JSON.stringify(values);
}

export function rowValues(entity: string): string[] {
  const values = JSON.parse(entity);
  if (rowKey(values) !== entity) throw new Error("Non-canonical row key");
  return values;
}

export function cellKey(tableId: string, entity: string, attribute: string): string {
  return JSON.stringify([tableId, rowValues(entity), attribute]);
}

export function cellRef(encoded: string): CellRef {
  const [table_id, key, attribute] = JSON.parse(encoded);
  if (typeof table_id !== "string" || !table_id || typeof attribute !== "string" || !attribute
      || cellKey(table_id, rowKey(key), attribute) !== encoded) throw new Error("Invalid cell key");
  return { table_id, key, attribute };
}

export function rowLabel(entity: string): string {
  return rowValues(entity).join(" · ");
}
