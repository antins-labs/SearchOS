import type { CoverageCell, TableSchema } from "./types";

/** Extract prose for the phone preview; wide Markdown tables are opened separately. */
export function mobileReportExcerpt(markdown: string, query: string): string {
  const body = markdown.split(/^#{1,6}\s*(信息来源|参考来源|引用来源|参考文献|来源|References|Sources)\s*$/im)[0];
  const lines = body.split("\n").map(line => line.trim()).filter(line =>
    line && line !== "_(empty body)_" && line !== "(empty body)" &&
    !line.startsWith("|") && !/^:?-{3,}/.test(line) &&
    line.replace(/^#{1,6}\s+/, "") !== query &&
    !/^#{1,6}\s*(数据对比表|信息来源|参考来源|引用来源|参考文献|来源|References|Sources)\s*$/i.test(line),
  );
  const plain = lines.join("\n").replace(/^#{1,6}\s+/gm, "").replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/\*\*/g, "");
  return plain.length > 280 ? `${plain.slice(0, 280)}…` : plain;
}
export interface ReportField { name: string; text: string; status: CoverageCell["status"]; conflict: boolean; links: string[] }
export interface ReportRow { id: string; title: string; summary: string; date: string; fields: ReportField[]; sources: string[]; needsReview: boolean }

const TITLE = /^(标题|名称|名字|title|name)$/i;
const SUMMARY = /^(事件概述|摘要|概述|简介|说明|summary|description|overview)$/i;
const DATE = /^(发布时间|发布日期|日期|时间|published_at|published|date|time)$/i;
const SOURCE = /来源|链接|source|url|link/i;

/** Only real web/local source URLs become actionable; never execute model text. */
export function reportSourceLinks(text: string): string[] {
  const candidates = text.match(/(?:https?:\/\/|local:\/\/)[^\s<>\[\]"')]+/gi) ?? [];
  return [...new Set(candidates.map(value => value.replace(/[，。；,;]+$/, "")).filter(value => {
    try {
      const url = new URL(value);
      return ["http:", "https:", "local:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password;
    } catch { return false; }
  }))];
}

export function reportRows(table: TableSchema, cells: Record<string, CoverageCell>): ReportRow[] {
  return table.entities.map(entity => {
    const fields = table.attributes.map(name => {
      const cell = cells[`${table.table_id}/${entity}.${name}`];
      const text = (Array.isArray(cell?.value) ? cell.value.join("\n\n") : cell?.value ?? "").trim();
      return { name, text, status: cell?.status ?? "missing", conflict: !!cell?.has_conflict, links: SOURCE.test(name) ? reportSourceLinks(text) : [] };
    });
    const available = fields.filter(field => field.text && field.status !== "missing");
    const title = available.find(field => TITLE.test(field.name))?.text || entity;
    const summary = (available.find(field => SUMMARY.test(field.name)) ?? available.find(field => !TITLE.test(field.name) && !DATE.test(field.name) && !SOURCE.test(field.name)))?.text ?? "";
    return {
      id: entity, title, summary: summary.slice(0, 160),
      date: available.find(field => DATE.test(field.name))?.text ?? "",
      fields, sources: [...new Set(available.flatMap(field => field.links))],
      needsReview: fields.some(field => field.conflict || field.status === "uncertain" || field.status === "hard_cell"),
    };
  });
}
