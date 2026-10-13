import type { EvidenceNode, WSEvent } from "./types";

const INVALID_NUMBERED_LINK_RE = /\[([^\]\n]*(?:资料|source)\s*(\d+)[^\]\n]*)\]\(invalid-local-reference\)/gi;
const WEB_URL_PATTERN = String.raw`https?:\/\/[^\]\s<>]+`;
const ADJACENT_BRACKETED_WEB_LINK_RE = new RegExp(
  `\\[(${WEB_URL_PATTERN})\\]\\[(${WEB_URL_PATTERN})\\]`,
  "g",
);
const STANDALONE_BRACKETED_WEB_LINK_RE = new RegExp(
  `(?<!!)\\[(${WEB_URL_PATTERN})\\](?!\\s*[\\[(:])`,
  "g",
);

function locatorLabel(loc: Record<string, unknown>): string {
  const range = (prefix: string, start: unknown, end: unknown) => (
    typeof start === "number" ? `${prefix}${start}${typeof end === "number" && end !== start ? `-${end}` : ""}` : ""
  );
  switch (loc.kind) {
    case "pdf_region": return range("P", loc.page_start, loc.page_end);
    case "line_range": return range("L", loc.start_line, loc.end_line);
    case "record_range": return range("R", loc.record_start, loc.record_end);
    case "slide_object": return typeof loc.slide_number === "number" ? `Slide ${loc.slide_number}` : "";
    case "cell_range": return `${loc.sheet_name ?? ""}!${loc.range ?? ""}`;
    case "docx_block": return `DOCX:${loc.cell || (Array.isArray(loc.path) ? loc.path.join("/") : loc.part) || ""}`;
    case "dom_range": return `DOM:${loc.path ?? ""}`;
    case "json_path": return `JSON:${loc.path || "/"}`;
    case "image_region": return `Image:${loc.frame ?? 1}`;
    default: return "";
  }
}

/** Use this turn's actual source records, including replayed history. No I/O. */
export function localCitationLabels(events: WSEvent[], evidence: EvidenceNode[] = []): Record<string, string> {
  const labels: Record<string, string> = {};
  const add = (ref: unknown, file: unknown, locators: unknown, location?: unknown) => {
    if (typeof ref !== "string" || !ref.startsWith("local://") || typeof file !== "string" || !file) return;
    const name = file.split(/[\\/]/).pop() || file;
    const loc = typeof location === "string" ? location : Array.isArray(locators)
      ? Array.from(new Set(locators.filter((item) => item && typeof item === "object").map(locatorLabel))).filter(Boolean).join(", ")
      : "";
    labels[ref] = loc ? `${name} · ${loc}` : name;
  };
  for (const node of evidence) {
    const source = node.local_source_metadata;
    if (source) add(node.source, source.file_name, source.locators);
  }
  for (const event of events) {
    const data = (event.data ?? {}) as Record<string, unknown>;
    if (event.type !== "trajectory" || data.type !== "local_read_observed") continue;
    try {
      const observation = typeof data.observation === "string"
        ? JSON.parse(data.observation) : data.observation;
      if (!observation || typeof observation !== "object") continue;
      add(observation.ref_id, observation.file, observation.locators, observation.location_label);
      // Older observations store the native compact reference in the tool header.
      const header = typeof observation.tool_content === "string" ? observation.tool_content.split("\n\n", 1)[0] : "";
      const nativeRef = observation.tool_ref_id || header.match(/^Source: (local:\/\/\S+)$/m)?.[1];
      add(nativeRef, observation.file, observation.locators, observation.location_label);
    } catch { /* Ignore an incomplete streamed record; the next update can supply it. */ }
  }
  return labels;
}

type CitationNode = {
  type: string;
  value?: string;
  url?: string;
  children?: CitationNode[];
};

/** Turn prose source handles into links before ReactMarkdown renders them.
 * Work on Markdown nodes so existing links and code blocks remain intact. */
export function remarkLocalCitations(sourceLabels: Record<string, string> = {}) {
  return (tree: CitationNode) => {
    const numbers = new Map<string, number>();
    const label = (url: string) => {
      if (sourceLabels[url]) return sourceLabels[url];
      if (!numbers.has(url)) numbers.set(url, numbers.size + 1);
      return `查看原文 ${numbers.get(url)}`;
    };
    const link = (url: string): CitationNode => ({
      type: "link", url, children: [{ type: "text", value: label(url) }],
    });
    const splitSources = (value: string): CitationNode[] => {
      const nodes: CitationNode[] = [];
      let end = 0;
      // Local handles use ASCII URI characters; punctuation belongs to prose.
      for (const match of value.matchAll(/local:\/\/[A-Za-z0-9._~:/?#=&%-]+/g)) {
        const url = match[0].replace(/[.,;:!?]+$/, "");
        if (!/^local:\/\/[^/]+\/[^/]+/.test(url)) continue;
        const start = match.index!;
        if (start > end) nodes.push({ type: "text", value: value.slice(end, start) });
        nodes.push(link(url));
        end = start + url.length;
      }
      if (end < value.length) nodes.push({ type: "text", value: value.slice(end) });
      return nodes;
    };
    const visit = (node: CitationNode) => {
      if (node.type === "link") {
        // Markdown autolinks also expose the entire opaque handle as the label.
        if (node.url?.startsWith("local://") && (sourceLabels[node.url]
          || (node.children?.length === 1 && node.children[0].value === node.url))) {
          node.children = [{ type: "text", value: label(node.url) }];
        }
        return;
      }
      if (node.type === "linkReference" || !node.children) return;
      node.children = node.children.flatMap((child) => {
        if (child.type === "text") return splitSources(child.value ?? "");
        // Models often put a standalone source handle inside inline backticks.
        if (child.type === "inlineCode" && child.value?.startsWith("local://")
          && !/\s/.test(child.value)) return [link(child.value)];
        visit(child);
        return [child];
      });
    };
    visit(tree);
  };
}

/**
 * Older Local runs may contain a numbered citation whose model-mutated URL was
 * rejected by the server. The Evidence Graph preserves the canonical sources
 * in the same retrieval order, so the UI can repair those durable answers.
 */
export function repairLocalCitationLinks(markdown: string, sources: string[]): string {
  return markdown.replace(INVALID_NUMBERED_LINK_RE, (_match, label: string, rawIndex: string) => {
    const source = sources[Number(rawIndex) - 1];
    return source
      ? `[${label}](${source})`
      : `${label}（来源不可用）`;
  });
}

/** Normalize malformed bracketed web URLs before GFM autolinking. */
export function repairMalformedWebLinks(markdown: string): string {
  const link = (url: string) => `[${url}](<${url}>)`;
  const repair = (text: string) => text
    .replace(ADJACENT_BRACKETED_WEB_LINK_RE, (_match, first: string, second: string) => (
      first === second ? link(first) : `${link(first)} ${link(second)}`
    ))
    .replace(STANDALONE_BRACKETED_WEB_LINK_RE, (_match, url: string) => link(url));
  let fence: { marker: string; length: number } | null = null;
  return markdown.split("\n").map((line) => {
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})/)?.[1];
    if (fence) {
      if (marker?.[0] === fence.marker && marker.length >= fence.length) fence = null;
      return line;
    }
    if (marker) {
      fence = { marker: marker[0], length: marker.length };
      return line;
    }
    let output = "";
    let cursor = 0;
    for (const match of line.matchAll(/(`+)(.*?)\1/g)) {
      const start = match.index ?? 0;
      output += repair(line.slice(cursor, start)) + match[0];
      cursor = start + match[0].length;
    }
    return output + repair(line.slice(cursor));
  }).join("\n");
}
