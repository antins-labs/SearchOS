/** Pure helpers for exec/skill timeline previews and detail dialogs. */

export type ExecArgsSummary = {
  code: string;
  argv: string[];
  commandLine: string;
  codeLines: number;
  detail: string;
};

export type ExecResultSummary = {
  exitCode: number | null;
  failed: boolean;
  stdout: string;
  stderr: string;
  stdoutChars: number;
  stderrChars: number;
  truncated: boolean;
  metaLine: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function argvLine(argv: string[]): string {
  return argv.map((part) => (
    /\s/.test(part) ? `"${part.replace(/"/g, '\\"')}"` : part
  )).join(" ");
}

/** Extract code / argv from a tool-call arguments string (JSON or Python-ish). */
export function parseExecArgs(raw: string): ExecArgsSummary {
  const empty: ExecArgsSummary = {
    code: "", argv: [], commandLine: "", codeLines: 0, detail: "Exec",
  };
  if (!raw.trim()) return empty;

  let code = "";
  let argv: string[] = [];
  const parsed = parseJson(raw);
  const obj = asRecord(parsed);
  if (obj) {
    if (typeof obj.code === "string") code = obj.code;
    if (Array.isArray(obj.argv)) {
      argv = obj.argv.filter((item): item is string => typeof item === "string");
    } else if (typeof obj.argv === "string") {
      argv = [obj.argv];
    }
  } else {
    const codeMatch = raw.match(/["']code["']\s*:\s*["']([\s\S]*?)["']\s*(?:,|})/);
    if (codeMatch) code = codeMatch[1].replace(/\\n/g, "\n").replace(/\\"/g, '"');
  }

  const commandLine = argv.length ? argvLine(argv) : "";
  const codeLines = code ? code.split(/\r?\n/).length : 0;
  let detail = "Exec";
  if (codeLines > 0) detail = `python · ${codeLines} 行`;
  else if (commandLine) detail = commandLine.length > 72 ? `${commandLine.slice(0, 72)}…` : commandLine;

  return { code, argv, commandLine, codeLines, detail };
}

function streamText(
  root: Record<string, unknown>,
  stream: "stdout" | "stderr",
): { text: string; totalChars: number; truncated: boolean } {
  const direct = root[stream];
  const text = typeof direct === "string" ? direct : "";
  const streams = asRecord(root.streams);
  const meta = asRecord(streams?.[stream]);
  const totalChars = typeof meta?.total_chars === "number"
    ? meta.total_chars
    : text.length;
  const truncated = Boolean(meta?.truncated || meta?.log_truncated);
  return { text, totalChars, truncated };
}

/** Summarize an exec observation JSON (or plain-text failure). */
export function summarizeExecResult(raw: string): ExecResultSummary {
  const parsed = asRecord(parseJson(raw));
  if (!parsed) {
    const text = raw.trim();
    return {
      exitCode: null,
      failed: false,
      stdout: text,
      stderr: "",
      stdoutChars: text.length,
      stderrChars: 0,
      truncated: false,
      metaLine: text ? "output" : "无输出",
    };
  }

  const exitRaw = parsed.exit_code;
  const exitCode = typeof exitRaw === "number" ? exitRaw : null;
  const status = typeof parsed.status === "string" ? parsed.status : "";
  const failed = status === "error" || status === "failed" || status === "cancelled"
    || (exitCode != null && exitCode !== 0);
  const out = streamText(parsed, "stdout");
  const err = streamText(parsed, "stderr");
  const truncated = out.truncated || err.truncated;

  const bits: string[] = [];
  if (exitCode != null) bits.push(`exit ${exitCode}`);
  else if (status) bits.push(status);
  else bits.push(failed ? "failed" : "ok");
  if (out.totalChars) bits.push(`stdout ${out.totalChars}`);
  if (err.totalChars) bits.push(`stderr ${err.totalChars}`);
  if (truncated) bits.push("truncated");

  return {
    exitCode,
    failed,
    stdout: out.text,
    stderr: err.text,
    stdoutChars: out.totalChars,
    stderrChars: err.totalChars,
    truncated,
    metaLine: bits.join(" · "),
  };
}

/** Pretty-print JSON when possible; otherwise return original text. */
export function formatPreviewText(raw: string): string {
  if (!raw.trim()) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

export function clipLines(text: string, maxLines: number, maxChars = 4000): string {
  const clipped = text.length > maxChars ? `${text.slice(0, maxChars)}\n…` : text;
  const lines = clipped.split(/\r?\n/);
  if (lines.length <= maxLines) return clipped;
  return `${lines.slice(0, maxLines).join("\n")}\n…`;
}

export function isCodeTool(detail: { tool?: string; kind?: string } | null | undefined): boolean {
  if (!detail) return false;
  return detail.tool === "exec" || detail.kind === "skill";
}
