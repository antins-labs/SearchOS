"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";
import { API_BASE, getHealth } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";

/** SearchOS mark — a large ring enclosing a smaller one (大包小), close radii,
 *  brand-blue gradient stroke. Doubles as a "focus / aperture" motif. */
function OrbMark({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" className={className} aria-hidden>
      <defs>
        <linearGradient id="orbmark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2f6bff" />
          <stop offset="0.55" stopColor="#4a86ff" />
          <stop offset="1" stopColor="#7ab6ff" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="8.2" stroke="url(#orbmark)" strokeWidth="1.7" />
      <circle cx="12" cy="12" r="5" stroke="url(#orbmark)" strokeWidth="1.7" opacity="0.85" />
    </svg>
  );
}

interface Props {
  onSubmit: (query: string, opts: { entities?: string[]; attrs?: string[] }) => void;
  initialQuery?: string;
  error?: string | null;
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-md border border-black/10 bg-black/[0.03] px-1.5 py-0.5 font-mono text-[10px] leading-none text-gray-500 dark:border-white/10 dark:bg-white/5 dark:text-zinc-300">
      {children}
    </kbd>
  );
}

const COMMANDS = [
  { cmd: "/schema", hint: "pin entities & attributes manually" },
];

const SUGGESTIONS: { label: string; text: string; c1: string; c2: string; glow: string }[] = [
  {
    label: "Wide table",
    text: "Compare the top GPU cloud providers on price, regions, and SLA",
    c1: "#2f6bff",
    c2: "#1d4ed8",
    glow: "hover:shadow-blue-500/20",
  },
  {
    label: "Enumerate",
    text: "List every Fields Medalist since 2000 with institution and country",
    c1: "#4a86ff",
    c2: "#3b76f0",
    glow: "hover:shadow-blue-400/20",
  },
  {
    label: "Timeline",
    text: "Which EU countries banned single-use plastics, and when?",
    c1: "#7ab6ff",
    c2: "#5b9bff",
    glow: "hover:shadow-sky-400/20",
  },
];

const API_HOST = API_BASE.replace(/^https?:\/\//, "");

export default function EntryScreen({ onSubmit, initialQuery, error }: Props) {
  const [query, setQuery] = useState(initialQuery ?? "");
  const [selected, setSelected] = useState(0);
  const [inputFocused, setInputFocused] = useState(false);
  const [cmdError, setCmdError] = useState<string | null>(null);
  const [showSchema, setShowSchema] = useState(false);
  const [entities, setEntities] = useState("");
  const [attrs, setAttrs] = useState("");
  const [health, setHealth] = useState<{ status: string; version?: string } | null | undefined>(undefined);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const slashTyping = /^\/[a-z]*$/i.test(query);
  const matches = slashTyping ? COMMANDS.filter((c) => c.cmd.startsWith(query.toLowerCase())) : [];
  const menuOpen = matches.length > 0 && inputFocused;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    let alive = true;
    const check = () => getHealth().then((h) => alive && setHealth(h));
    check();
    const iv = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);

  // Autosize the textarea up to ~6 lines
  useEffect(() => {
    const fit = () => {
      const el = inputRef.current;
      if (!el) return;
      el.style.height = "0px";
      el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [query]);

  const choose = (cmd: string) => {
    if (cmd === "/schema") {
      setShowSchema((v) => !v);
      setQuery("");
    }
    inputRef.current?.focus();
  };

  const submit = () => {
    const text = query.trim();
    if (!text) return;
    if (text.startsWith("/")) {
      const token = text.split(/\s+/)[0];
      setCmdError(`unknown or incomplete command: ${token}`);
      return;
    }
    const csv = (s: string) => {
      const items = s.split(",").map((x) => x.trim()).filter(Boolean);
      return items.length > 0 ? items : undefined;
    };
    onSubmit(text, {
      entities: showSchema ? csv(entities) : undefined,
      attrs: showSchema ? csv(attrs) : undefined,
    });
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    if (menuOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => (s + 1) % matches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => (s - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        choose(matches[selected].cmd);
        return;
      }
      if (e.key === "Escape") {
        setQuery("");
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const statusDot =
    health === undefined ? (
      <span className="flex items-center gap-1.5 text-gray-400 dark:text-zinc-600">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> connecting…
      </span>
    ) : health ? (
      <span className="flex items-center gap-1.5 text-gray-500 dark:text-zinc-500">
        <span className="glow-pulse h-1.5 w-1.5 rounded-full bg-emerald-500" /> connected
        <span className="hidden font-mono opacity-60 md:inline">· {API_HOST}</span>
      </span>
    ) : (
      <span className="flex items-center gap-1.5 text-gray-500 dark:text-zinc-500">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500" /> offline — run{" "}
        <span className="font-mono text-gray-600 dark:text-zinc-400">./start.sh api</span>
      </span>
    );

  return (
    <div className="relative flex h-screen flex-col overflow-y-auto">
      {/* decorative ambient orbs */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="float-slow absolute -left-24 top-10 h-80 w-80 rounded-full bg-blue-400/15 blur-3xl dark:bg-blue-500/20" />
        <div className="float-slow absolute right-[-6rem] top-1/3 h-96 w-96 rounded-full bg-indigo-400/15 blur-3xl dark:bg-indigo-500/20" style={{ animationDelay: "-3.5s" }} />
        <div className="float-slow absolute bottom-[-5rem] left-1/3 h-72 w-72 rounded-full bg-sky-400/10 blur-3xl dark:bg-sky-500/15" style={{ animationDelay: "-7s" }} />
      </div>

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      <main className="relative z-10 mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-6 py-16">
        {/* Wordmark */}
        <div className="rise-in flex flex-col items-center text-center">
          <h1 className="wordmark text-6xl font-semibold tracking-tight sm:text-7xl">SearchOS</h1>
          <p className="mt-5 text-base text-gray-500 dark:text-zinc-400 sm:text-lg">
            the agentic search operating system
          </p>
        </div>

        {/* Input */}
        <div className="rise-in relative mt-12" style={{ animationDelay: "60ms" }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="surface group flex items-center gap-3 rounded-2xl px-5 py-4 shadow-lg shadow-black/5 transition-all focus-within:ring-1 focus-within:ring-blue-500/40 dark:shadow-black/30"
          >
            <OrbMark size={22} className="shrink-0 transition-transform group-focus-within:rotate-90" />
            <div className="relative min-w-0 flex-1">
              {query === "" && (
                <span className="pointer-events-none absolute inset-x-0 top-0 truncate leading-8 text-gray-400 dark:text-zinc-500">
                  Ask anything — agents fan out and forge the answer…
                </span>
              )}
              <textarea
                ref={inputRef}
                rows={1}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setSelected(0);
                  setCmdError(null);
                }}
                onKeyDown={handleKeyDown}
                onFocus={() => setInputFocused(true)}
                onBlur={() => setInputFocused(false)}
                spellCheck={false}
                className="block w-full resize-none bg-transparent text-base leading-8 text-gray-800 caret-blue-500 outline-none dark:text-zinc-100"
              />
            </div>
            {query === "" && (
              <button
                type="button"
                onClick={() => {
                  setQuery("/");
                  inputRef.current?.focus();
                }}
                title="Slash commands"
                className="hidden shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] text-gray-400 transition-colors hover:text-blue-600 sm:flex dark:text-zinc-500 dark:hover:text-blue-400"
              >
                <Kbd>/</Kbd> commands
              </button>
            )}
            <button
              type="submit"
              aria-label="Search"
              className="shrink-0 rounded-xl bg-blue-500/15 p-2.5 text-blue-600 transition-colors hover:bg-blue-500/25 dark:text-blue-400"
            >
              <ArrowUp size={18} />
            </button>
          </form>

          {/* Slash command menu */}
          {menuOpen && (
            <div className="surface absolute inset-x-0 top-full z-10 mt-2 overflow-hidden rounded-xl shadow-xl">
              {matches.map((c, i) => (
                <button
                  key={c.cmd}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(c.cmd)}
                  onMouseEnter={() => setSelected(i)}
                  className={`flex w-full items-baseline gap-3 px-4 py-2 text-left text-xs ${
                    i === selected ? "bg-blue-500/10" : ""
                  }`}
                >
                  <span
                    className={`w-16 shrink-0 font-mono ${
                      i === selected
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-gray-600 dark:text-zinc-400"
                    }`}
                  >
                    {c.cmd}
                  </span>
                  <span className="truncate text-gray-400 dark:text-zinc-600">{c.hint}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Manual schema */}
        {showSchema && (
          <div className="rise-in mt-3 grid grid-cols-2 gap-2 text-xs">
            <label className="surface flex items-center gap-2 rounded-xl px-3 py-2">
              <span className="shrink-0 text-gray-400 dark:text-zinc-600">entities</span>
              <input
                value={entities}
                onChange={(e) => setEntities(e.target.value)}
                placeholder="A, B, C"
                spellCheck={false}
                className="w-full bg-transparent outline-none placeholder:text-gray-300 dark:text-zinc-200 dark:placeholder:text-zinc-700"
              />
            </label>
            <label className="surface flex items-center gap-2 rounded-xl px-3 py-2">
              <span className="shrink-0 text-gray-400 dark:text-zinc-600">attrs</span>
              <input
                value={attrs}
                onChange={(e) => setAttrs(e.target.value)}
                placeholder="x, y, z"
                spellCheck={false}
                className="w-full bg-transparent outline-none placeholder:text-gray-300 dark:text-zinc-200 dark:placeholder:text-zinc-700"
              />
            </label>
          </div>
        )}

        {/* Errors */}
        {(cmdError || error) && (
          <p className="mt-3 text-xs text-red-500 dark:text-red-400">{cmdError ?? error}</p>
        )}

        {/* Example cards — hidden while the slash menu is open to avoid overlap */}
        {!menuOpen && (
          <div
            className="rise-in mt-8 grid grid-cols-1 gap-3 sm:grid-cols-3"
            style={{ animationDelay: "120ms" }}
          >
            {SUGGESTIONS.map((s) => (
              <button
                key={s.text}
                onClick={() => {
                  setQuery(s.text);
                  inputRef.current?.focus();
                }}
                className={`surface sheen group relative flex h-36 flex-col rounded-2xl p-4 text-left shadow-lg shadow-transparent transition-all duration-300 hover:-translate-y-1 ${s.glow}`}
              >
                <span
                  className="gradient-pan h-[3px] w-12 rounded-full"
                  style={{ backgroundImage: `linear-gradient(90deg, ${s.c1}, ${s.c2}, ${s.c1})` }}
                />
                <span className="mt-4 text-[11px] font-medium uppercase tracking-[0.18em] text-gray-400 dark:text-zinc-500">
                  {s.label}
                </span>
                <span className="mt-2 text-sm leading-relaxed text-gray-700 dark:text-zinc-200">
                  {s.text}
                </span>
                <ArrowUp
                  size={14}
                  className="mt-auto rotate-45 self-end text-gray-300 transition-all group-hover:translate-x-0.5 group-hover:text-blue-500 dark:text-zinc-700 dark:group-hover:text-blue-400"
                />
              </button>
            ))}
          </div>
        )}

      </main>

      {/* Pinned footer — secondary meta, kept out of the way of the hero */}
      <footer className="relative z-10 flex items-center justify-between gap-3 border-t border-black/5 px-6 py-3 text-xs text-gray-400 dark:border-white/5 dark:text-zinc-500">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <Kbd>↵</Kbd> search
          </span>
          <span className="hidden items-center gap-1.5 sm:flex">
            <Kbd>⇧ ↵</Kbd> newline
          </span>
        </div>
        <div className="flex items-center gap-3">
          {showSchema && <span className="text-violet-500 dark:text-violet-400">schema pinned</span>}
          {showSchema && <span className="opacity-30">·</span>}
          {statusDot}
        </div>
      </footer>
    </div>
  );
}
