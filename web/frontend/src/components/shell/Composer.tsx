"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp, Gauge, SlidersHorizontal, Square, X } from "lucide-react";

import { useSettings } from "@/components/settings/SettingsProvider";
import RunOverridesPopover from "@/components/settings/RunOverridesPopover";

export interface SubmitOpts {
  type?: string;
  entities?: string[];
  attrs?: string[];
}

interface Props {
  onSubmit: (query: string, opts: SubmitOpts) => void;
  /** When set, submitting while `running` steers the live run instead of being ignored. */
  onSteer?: (text: string) => void;
  /** When set, a stop button interrupts the live run while `running`. */
  onStop?: () => void;
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
  onSteer,
  onStop,
  running = false,
  variant = "bar",
  placeholder,
  autoFocus = false,
}: Props) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [showSchema, setShowSchema] = useState(false);
  const [showOverrides, setShowOverrides] = useState(false);
  const [entities, setEntities] = useState("");
  const [attrs, setAttrs] = useState("");
  const [sel, setSel] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const { overrides, clearOverrides } = useSettings();

  const overridesActive = overrides.effort != null || overrides.max_time != null;
  // Pinned schema follows the *content*, not the panel visibility — collapsing
  // the panel must not silently drop what the user typed.
  const pinnedRows = csv(entities);
  const pinnedCols = csv(attrs);
  const schemaPinned = !!(pinnedRows || pinnedCols);
  const overrideChip = [
    overrides.effort,
    overrides.max_time != null ? `${overrides.max_time}s` : null,
  ].filter(Boolean).join(" · ");

  const hero = variant === "hero";
  const slashTyping = /^\/[a-z]*$/i.test(text);
  const matches = slashTyping ? COMMANDS.filter((c) => c.cmd.startsWith(text.toLowerCase())) : [];
  const menuOpen = matches.length > 0 && focused && !menuDismissed;

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
    const m = text.trim().match(/^\/(wide|deep|local)\s+([\s\S]+)$/i);
    const body = (m ? m[2] : text).trim();
    if (!body || body.startsWith("/")) return;
    if (running) {
      // Mid-run: steer the live orchestrator rather than queue a new search.
      if (!onSteer) return;
      onSteer(body);
      setText("");
      return;
    }
    onSubmit(body, {
      type: m?.[1]?.toLowerCase(),
      entities: pinnedRows,
      attrs: pinnedCols,
    });
    setText("");
  };

  const clearSchema = () => {
    setEntities("");
    setAttrs("");
    setShowSchema(false);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    if (menuOpen) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => (s + 1) % matches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => (s - 1 + matches.length) % matches.length); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); choose(matches[sel].cmd); return; }
      if (e.key === "Escape") { setMenuDismissed(true); return; }
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
          title="Pin table rows & columns (optional)"
          className={`mb-0.5 shrink-0 rounded-lg p-1.5 transition-colors ${
            showSchema || schemaPinned ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"
          }`}
        >
          <SlidersHorizontal size={hero ? 17 : 15} />
        </button>
        <button
          type="button"
          onClick={() => setShowOverrides((v) => !v)}
          title="Run overrides"
          className={`mb-0.5 shrink-0 rounded-lg p-1.5 transition-colors ${
            showOverrides || overridesActive ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"
          }`}
        >
          <Gauge size={hero ? 17 : 15} />
        </button>
        {schemaPinned && !showSchema && (
          <span className="mb-1 flex shrink-0 items-center gap-1 rounded-md bg-clay px-1.5 py-0.5 text-[11px] text-accent-ink">
            {pinnedRows?.length ?? 0} rows × {pinnedCols?.length ?? 0} cols
            <button type="button" aria-label="Clear pinned schema" onClick={clearSchema}
              className="rounded-sm transition-opacity hover:opacity-70">
              <X size={11} />
            </button>
          </span>
        )}
        {overridesActive && (
          <span className="mb-1 flex shrink-0 items-center gap-1 rounded-md bg-clay px-1.5 py-0.5 text-[11px] text-accent-ink">
            {overrideChip}
            <button type="button" aria-label="Clear run overrides" onClick={clearOverrides}
              className="rounded-sm transition-opacity hover:opacity-70">
              <X size={11} />
            </button>
          </span>
        )}
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => { setText(e.target.value); setSel(0); setMenuDismissed(false); }}
          onKeyDown={onKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          spellCheck={false}
          placeholder={
            running
              ? onSteer
                ? "Searching… press Enter to steer the live run"
                : "Searching… type your next question"
              : placeholder ?? "Ask anything…"
          }
          className={`min-w-0 flex-1 resize-none bg-transparent leading-relaxed text-ink caret-accent outline-none placeholder:text-ink-faint disabled:opacity-50 ${
            hero ? "py-1 text-[16px]" : "py-0.5 text-[15px]"
          }`}
        />
        {running && onStop && (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop the run"
            title="Stop the run"
            className={`mb-0.5 shrink-0 rounded-xl border border-err/40 text-err transition-colors hover:bg-err/10 ${
              hero ? "p-2.5" : "p-2"
            }`}
          >
            <Square size={hero ? 16 : 14} fill="currentColor" />
          </button>
        )}
        <button
          type="submit"
          disabled={!text.trim() || (running && !onSteer)}
          aria-label={running && onSteer ? "Steer the live run" : "Send"}
          title={running && onSteer ? "Steer the live run" : undefined}
          className={`mb-0.5 shrink-0 rounded-xl bg-accent text-white transition-opacity hover:opacity-90 disabled:opacity-25 ${
            hero ? "p-2.5" : "p-2"
          }`}
        >
          <ArrowUp size={hero ? 18 : 16} />
        </button>
      </form>

      {/* manual schema row */}
      {showSchema && (
        <div className="rise-in mt-2">
          <div className="grid grid-cols-2 gap-2 text-[13px]">
            <label className="surface flex items-center gap-2 rounded-xl px-3 py-2 focus-within:border-line-strong">
              <span className="shrink-0 text-ink-faint">Rows</span>
              <input
                autoFocus
                value={entities}
                onChange={(e) => setEntities(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
                placeholder="Tesla, BYD, NIO"
                spellCheck={false}
                className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
              />
            </label>
            <label className="surface flex items-center gap-2 rounded-xl px-3 py-2 focus-within:border-line-strong">
              <span className="shrink-0 text-ink-faint">Cols</span>
              <input
                value={attrs}
                onChange={(e) => setAttrs(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
                placeholder="price, range, 0-100 km/h"
                spellCheck={false}
                className="w-full bg-transparent text-ink outline-none placeholder:text-ink-faint"
              />
            </label>
          </div>
          <div className="mt-1.5 flex items-baseline justify-between px-1 text-[11.5px] text-ink-faint">
            <span>Optional — pin the table&apos;s rows and columns (comma-separated). Leave empty and the orchestrator designs the schema itself.</span>
            {schemaPinned && (
              <button type="button" onClick={clearSchema} className="shrink-0 pl-3 text-ink-faint transition-colors hover:text-ink-dim">
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {/* per-run overrides popover */}
      {showOverrides && (
        <RunOverridesPopover direction={hero ? "down" : "up"} onClose={() => setShowOverrides(false)} />
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
