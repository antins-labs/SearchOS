"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp, SlidersHorizontal } from "lucide-react";

export interface SubmitOpts {
  type?: string;
  entities?: string[];
  attrs?: string[];
}

interface Props {
  onSubmit: (query: string, opts: SubmitOpts) => void;
  running?: boolean;
  /** "hero" = large landing composer, "bar" = compact in-conversation bar */
  variant?: "hero" | "bar";
  placeholder?: string;
  autoFocus?: boolean;
}

const COMMANDS = [
  { cmd: "/wide", hint: "Compare entities across attributes — forge a table" },
  { cmd: "/deep", hint: "Hunt down one hard-to-find fact" },
  { cmd: "/local", hint: "Search the local corpus" },
  { cmd: "/schema", hint: "Pin rows (entities) and cols (attributes)" },
];

const csv = (s: string) => {
  const items = s.split(",").map((x) => x.trim()).filter(Boolean);
  return items.length ? items : undefined;
};

export default function Composer({
  onSubmit,
  running = false,
  variant = "bar",
  placeholder,
  autoFocus = false,
}: Props) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [showSchema, setShowSchema] = useState(false);
  const [entities, setEntities] = useState("");
  const [attrs, setAttrs] = useState("");
  const [sel, setSel] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);

  const hero = variant === "hero";
  const slashTyping = /^\/[a-z]*$/i.test(text);
  const matches = slashTyping ? COMMANDS.filter((c) => c.cmd.startsWith(text.toLowerCase())) : [];
  const menuOpen = matches.length > 0 && focused;

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  // autosize
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, hero ? 200 : 160)}px`;
  }, [text, hero]);

  const choose = (cmd: string) => {
    if (cmd === "/schema") {
      setShowSchema((v) => !v);
      setText("");
    } else {
      setText(`${cmd} `);
    }
    ref.current?.focus();
  };

  const submit = () => {
    if (running) return;
    const m = text.trim().match(/^\/(wide|deep|local)\s+([\s\S]+)$/i);
    const body = (m ? m[2] : text).trim();
    if (!body || body.startsWith("/")) return;
    onSubmit(body, {
      type: m?.[1]?.toLowerCase(),
      entities: showSchema ? csv(entities) : undefined,
      attrs: showSchema ? csv(attrs) : undefined,
    });
    setText("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    if (menuOpen) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => (s + 1) % matches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => (s - 1 + matches.length) % matches.length); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); choose(matches[sel].cmd); return; }
      if (e.key === "Escape") { setText(""); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  return (
    <div className="relative w-full">
      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className={`surface flex items-end gap-2 transition-shadow focus-within:border-line-strong ${
          hero ? "rounded-2xl px-4 py-3.5 shadow-[0_2px_18px_rgba(21,34,56,0.06)]" : "rounded-2xl px-3.5 py-2.5"
        }`}
      >
        <button
          type="button"
          onClick={() => setShowSchema((v) => !v)}
          title="Manual schema"
          className={`mb-0.5 shrink-0 rounded-lg p-1.5 transition-colors ${
            showSchema ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"
          }`}
        >
          <SlidersHorizontal size={hero ? 17 : 15} />
        </button>
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => { setText(e.target.value); setSel(0); }}
          onKeyDown={onKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          disabled={running}
          spellCheck={false}
          placeholder={placeholder ?? (running ? "Searching…" : "Ask anything…")}
          className={`min-w-0 flex-1 resize-none bg-transparent leading-relaxed text-ink caret-accent outline-none placeholder:text-ink-faint disabled:opacity-50 ${
            hero ? "py-1 text-[16px]" : "py-0.5 text-[15px]"
          }`}
        />
        <button
          type="submit"
          disabled={running || !text.trim()}
          aria-label="Send"
          className={`mb-0.5 shrink-0 rounded-xl bg-accent text-white transition-opacity hover:opacity-90 disabled:opacity-25 ${
            hero ? "p-2.5" : "p-2"
          }`}
        >
          <ArrowUp size={hero ? 18 : 16} />
        </button>
      </form>

      {/* manual schema row */}
      {showSchema && (
        <div className="rise-in mt-2 grid grid-cols-2 gap-2 text-[13px]">
          <label className="surface flex items-center gap-2 rounded-xl px-3 py-2">
            <span className="shrink-0 text-ink-faint">Rows</span>
            <input value={entities} onChange={(e) => setEntities(e.target.value)} placeholder="A, B, C"
              spellCheck={false} className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint" />
          </label>
          <label className="surface flex items-center gap-2 rounded-xl px-3 py-2">
            <span className="shrink-0 text-ink-faint">Cols</span>
            <input value={attrs} onChange={(e) => setAttrs(e.target.value)} placeholder="x, y, z"
              spellCheck={false} className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint" />
          </label>
        </div>
      )}

      {/* slash menu */}
      {menuOpen && (
        <div className="surface absolute inset-x-0 top-full z-20 mt-2 overflow-hidden rounded-xl shadow-xl">
          {matches.map((c, i) => (
            <button
              key={c.cmd}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(c.cmd)}
              onMouseEnter={() => setSel(i)}
              className={`flex w-full items-baseline gap-3 px-4 py-2 text-left text-[13px] ${i === sel ? "bg-clay/50" : ""}`}
            >
              <span className={`w-16 shrink-0 font-mono ${i === sel ? "text-accent-ink" : "text-ink-dim"}`}>{c.cmd}</span>
              <span className="truncate text-ink-faint">{c.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
