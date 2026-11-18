/** Lightweight Python/shell highlighter — brand tokens only, no deps. */

import type { ReactNode } from "react";

export type CodeTokenKind = "kw" | "str" | "num" | "cmt" | "fn" | "op" | "plain";
export type CodeToken = { kind: CodeTokenKind; text: string };

const KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break",
  "class", "continue", "def", "del", "elif", "else", "except", "finally",
  "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
  "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);

const BUILTINS = new Set([
  "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
  "getattr", "hasattr", "int", "isinstance", "len", "list", "map", "max",
  "min", "open", "print", "range", "set", "sorted", "str", "sum", "tuple",
  "type", "zip", "skill",
]);

const TOKEN_CLASS: Record<CodeTokenKind, string> = {
  kw: "trace-tok-kw",
  str: "trace-tok-str",
  num: "trace-tok-num",
  cmt: "trace-tok-cmt",
  fn: "trace-tok-fn",
  op: "trace-tok-op",
  plain: "trace-tok-plain",
};

function push(tokens: CodeToken[], kind: CodeTokenKind, text: string) {
  if (!text) return;
  const last = tokens[tokens.length - 1];
  if (last && last.kind === kind) last.text += text;
  else tokens.push({ kind, text });
}

/** Tokenize Python-ish / shell snippets for timeline + dialog previews. */
export function tokenizePython(source: string): CodeToken[] {
  const tokens: CodeToken[] = [];
  let i = 0;
  const n = source.length;

  while (i < n) {
    const ch = source[i];

    if (ch === "#") {
      let j = i + 1;
      while (j < n && source[j] !== "\n") j += 1;
      push(tokens, "cmt", source.slice(i, j));
      i = j;
      continue;
    }

    if (ch === '"' || ch === "'") {
      const quote = ch;
      // triple quotes
      if (source.slice(i, i + 3) === quote.repeat(3)) {
        let j = i + 3;
        while (j < n && source.slice(j, j + 3) !== quote.repeat(3)) {
          if (source[j] === "\\") j += 2;
          else j += 1;
        }
        j = Math.min(n, j + 3);
        push(tokens, "str", source.slice(i, j));
        i = j;
        continue;
      }
      let j = i + 1;
      while (j < n && source[j] !== quote && source[j] !== "\n") {
        if (source[j] === "\\") j += 2;
        else j += 1;
      }
      if (j < n && source[j] === quote) j += 1;
      push(tokens, "str", source.slice(i, j));
      i = j;
      continue;
    }

    if (/[0-9]/.test(ch) || (ch === "." && /[0-9]/.test(source[i + 1] || ""))) {
      let j = i;
      while (j < n && /[0-9._xXbBoO]/.test(source[j])) j += 1;
      push(tokens, "num", source.slice(i, j));
      i = j;
      continue;
    }

    if (/[A-Za-z_]/.test(ch)) {
      let j = i + 1;
      while (j < n && /[A-Za-z0-9_]/.test(source[j])) j += 1;
      const word = source.slice(i, j);
      let k = j;
      while (k < n && /\s/.test(source[k])) k += 1;
      const call = source[k] === "(";
      const kind: CodeTokenKind = KEYWORDS.has(word)
        ? "kw"
        : call || BUILTINS.has(word)
          ? "fn"
          : "plain";
      push(tokens, kind, word);
      i = j;
      continue;
    }

    if (/[=+\-*/%<>!&|^~:.,;()[\]{}@]/.test(ch)) {
      let j = i + 1;
      // multi-char ops
      if (j < n && /[=<>!]/.test(ch) && source[j] === "=") j += 1;
      else if (ch === "-" && source[j] === ">") j += 1;
      else if ((ch === "*" || ch === "/" || ch === "<" || ch === ">") && source[j] === ch) j += 1;
      push(tokens, "op", source.slice(i, j));
      i = j;
      continue;
    }

    push(tokens, "plain", ch);
    i += 1;
  }

  return tokens;
}

export function highlightCode(source: string): ReactNode[] {
  return tokenizePython(source).map((token, index) => (
    <span key={index} className={TOKEN_CLASS[token.kind]}>{token.text}</span>
  ));
}
