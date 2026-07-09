"use client";

import Composer, { type SubmitOpts } from "@/components/shell/Composer";

interface Props {
  onSubmit: (q: string, opts: SubmitOpts) => void;
  error?: string | null;
}

const SUGGESTIONS = [
  { label: "Wide table", text: "Compare the top GPU cloud providers on price, regions, and SLA" },
  { label: "Enumerate", text: "List every Fields Medalist since 2000 with institution and country" },
  { label: "Timeline", text: "Which EU countries banned single-use plastics, and when?" },
  { label: "Deep dive", text: "Find the exact amount and date of Anthropic's latest funding round" },
];

export default function Landing({ onSubmit, error }: Props) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      <div className="w-full max-w-2xl">
        <h1 className="wordmark rise-in mb-9 text-center text-6xl tracking-tight sm:text-7xl">SearchOS</h1>

        {/* relative z-20: the rise-in animation (fill: both) makes this and the
            suggestion grid below persistent stacking contexts, so without an
            explicit order the composer's popovers paint underneath the cards. */}
        <div className="rise-in relative z-20" style={{ animationDelay: "60ms" }}>
          <Composer onSubmit={onSubmit} variant="hero" autoFocus placeholder="Ask anything…" />
        </div>

        {error && <p className="mt-3 text-center text-[13px] text-err">{error}</p>}

        <div className="rise-in mt-5 grid grid-cols-2 gap-2.5" style={{ animationDelay: "120ms" }}>
          {SUGGESTIONS.map((s) => (
            <button
              key={s.text}
              onClick={() => onSubmit(s.text, {})}
              className="surface group flex flex-col gap-1 rounded-xl px-4 py-3 text-left transition-colors hover:border-line-strong hover:bg-surface-2"
            >
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent-ink">{s.label}</span>
              <span className="line-clamp-2 text-[13.5px] leading-snug text-ink-dim group-hover:text-ink">{s.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
