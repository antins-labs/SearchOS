"use client";

import { Fragment, type ReactNode } from "react";
import { turnActivitySegments, type Turn } from "@/lib/conversation";
import { foldWorkers } from "@/lib/derive";
import OrchestrationCard from "./OrchestrationCard";

export default function TurnActivity({ turn, onOpen, children }: {
  turn: Turn;
  onOpen: () => void;
  children?: ReactNode;
}) {
  const segments = turnActivitySegments(turn.events, turn.followUps);
  return <>{segments.map((segment, index) => {
    const latest = index === segments.length - 1;
    const showTrace = segment.events.length > 0 || (latest && turn.status === "running");
    return <Fragment key={segment.key}>
      {segment.followUp && (
        <div className="my-6 flex justify-end">
          <div className="max-w-[90%] rounded-2xl rounded-br-md border border-accent/30 bg-clay/40 px-4 py-2.5 sm:max-w-[80%]">
            <div className="mb-0.5 text-[10px] font-medium text-accent-ink">
              {segment.followUp.mode === "after_tool" ? "工具返回后加入" : segment.followUp.mode === "immediate" ? "立即引导" : "运行中追问"}
            </div>
            <div className="whitespace-pre-wrap break-words text-[14px] leading-relaxed text-ink">{segment.followUp.text}</div>
          </div>
        </div>
      )}
      {(showTrace || latest) && (
        <div className="flex gap-2.5 sm:gap-3.5">
          <div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent font-serif text-[12px] font-semibold text-white sm:h-7 sm:w-7 sm:text-[14px]">S</div>
          <div className="min-w-0 flex-1">
            {showTrace && <div className="mb-4">
              <OrchestrationCard events={segment.events} priorEvents={segment.priorEvents}
                searchState={latest ? turn.searchState : null}
                status={latest ? turn.status : "idle"} continued={!latest}
                workers={latest ? turn.workers : foldWorkers([...segment.priorEvents, ...segment.events])}
                sourceMode={turn.sourceMode} onOpen={onOpen} />
            </div>}
            {latest && children}
          </div>
        </div>
      )}
    </Fragment>;
  })}</>;
}
