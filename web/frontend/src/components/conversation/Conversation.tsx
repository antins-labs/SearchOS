"use client";

import { useEffect, useRef } from "react";
import Composer, { type SubmitOpts } from "@/components/shell/Composer";
import OrchestrationCard from "./OrchestrationCard";
import Answer from "./Answer";
import CoverageTable from "@/components/coverage/CoverageTable";
import type { Turn } from "@/lib/conversation";

interface Props {
  turns: Turn[];
  running: boolean;
  stopping?: boolean;
  onSubmit: (q: string, opts: SubmitOpts) => void;
  onSteer?: (text: string) => void;
  onStop?: () => void;
  onOpenDrawer: (turnId: string) => void;
  registerTurnRef?: (id: string, el: HTMLDivElement | null) => void;
}

export default function Conversation({ turns, running, stopping = false, onSubmit, onSteer, onStop, onOpenDrawer, registerTurnRef }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  // Follow the bottom only while a search is live; a freshly loaded historical
  // session should rest at the top, not jump to its references.
  useEffect(() => {
    if (running) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, running]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[760px] px-3 pb-6 pt-16 sm:px-5 min-[1180px]:px-6 min-[1180px]:py-8">
          {turns.map((t) => (
            <TurnView
              key={t.id}
              turn={t}
              onOpen={() => onOpenDrawer(t.id)}
              registerRef={registerTurnRef ? (el) => registerTurnRef(t.id, el) : undefined}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-line bg-paper">
        <div className="mx-auto max-w-[760px] px-3 py-3 sm:px-5 min-[1180px]:px-6 min-[1180px]:py-4">
          <Composer onSubmit={onSubmit} onSteer={onSteer} onStop={onStop} running={running} stopping={stopping} variant="bar" />
        </div>
      </div>
    </div>
  );
}

function TurnView({ turn, onOpen, registerRef }: { turn: Turn; onOpen: () => void; registerRef?: (el: HTMLDivElement | null) => void }) {
  const done = turn.status === "completed";
  const hasTable = Object.keys(turn.searchState?.coverage_map?.cells ?? {}).some((k) => !k.startsWith("_"));

  return (
    <div ref={registerRef} className="mb-10 scroll-mt-6 last:mb-2">
      {/* user message */}
      <div className="mb-6 flex justify-end">
        <div className="max-w-[90%] rounded-2xl rounded-br-md border border-line bg-surface px-4 py-2.5 text-[15px] leading-relaxed text-ink sm:max-w-[80%]">
          {turn.query}
        </div>
      </div>

      {/* live follow-ups steered into this turn mid-run */}
      {(turn.followUps ?? []).map((f, i) => (
        <div key={i} className="rise-in -mt-3 mb-6 flex justify-end">
          <div className="max-w-[80%] rounded-2xl rounded-br-md border border-accent/30 bg-clay/40 px-4 py-2.5">
            <div className="mb-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent-ink">
              Steered mid-run
            </div>
            <div className="text-[14px] leading-relaxed text-ink">{f}</div>
          </div>
        </div>
      ))}

      {/* assistant turn */}
      <div className="flex gap-2.5 sm:gap-3.5">
        <div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent font-serif text-[12px] font-semibold text-white sm:h-7 sm:w-7 sm:text-[14px]">
          S
        </div>
        <div className="min-w-0 flex-1">
          {/* Restored earlier turns carry no per-turn trajectory — plain Q&A. */}
          {(turn.events.length > 0 || turn.status === "running") && (
            <div className="mb-4">
              <OrchestrationCard
                events={turn.events}
                searchState={turn.searchState}
                status={turn.status}
                workers={turn.workers}
                onOpen={onOpen}
              />
            </div>
          )}

          {turn.error && (
            <p className="mb-4 rounded-lg border border-err/30 bg-err/5 px-3 py-2 text-[13px] text-err">{turn.error}</p>
          )}

          {done && turn.answer && (
            <div className="mb-5">
              <Answer markdown={turn.answer} />
            </div>
          )}

          {done && hasTable && (
            <div className="mb-4 overflow-hidden rounded-xl border border-line">
              <div className="border-b border-line bg-surface-2 px-3.5 py-2">
                <span className="font-serif text-[14px] font-semibold text-ink">Final table</span>
              </div>
              <div className="max-h-[440px] overflow-auto">
                <CoverageTable
                  coverageMap={turn.searchState?.coverage_map ?? null}
                  evidence={turn.searchState?.evidence_graph?.nodes ?? []}
                />
              </div>
            </div>
          )}

          {done && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-dim">
              {typeof turn.meta.coverageScore === "number" && (
                <span>Coverage <b className="font-semibold text-ink">{(turn.meta.coverageScore * 100).toFixed(0)}%</b></span>
              )}
              {typeof turn.meta.evidenceCount === "number" && (
                <span>Evidence <b className="font-semibold text-ink">{turn.meta.evidenceCount}</b></span>
              )}
              {typeof turn.meta.elapsed === "number" && (
                <span>Time <b className="font-semibold text-ink">{turn.meta.elapsed.toFixed(1)}s</b></span>
              )}
              {turn.meta.verdict && <span className="text-ink-faint">{turn.meta.verdict}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
