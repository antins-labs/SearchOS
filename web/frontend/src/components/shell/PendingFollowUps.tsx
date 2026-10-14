"use client";

import { CornerDownLeft, ListStart, Loader2, Trash2 } from "lucide-react";
import type { LiveFollowUpController } from "@/hooks/useLiveFollowUps";

export default function PendingFollowUps({ queue, running }: {
  queue: LiveFollowUpController;
  running: boolean;
}) {
  if (!queue.pending.length) return null;
  return (
    <div aria-label="待处理追问" className="mx-3 -mb-3 overflow-hidden rounded-t-2xl border border-b-0 border-line bg-surface pb-3">
      {queue.pending.map((message) => {
        const busy = queue.working.has(message.id);
        const guiding = message.mode === "immediate";
        return (
          <div key={message.id} className="flex items-start gap-2 px-3 py-2 text-[13px] text-ink-dim [&+div]:border-t [&+div]:border-line">
            <ListStart size={14} className="mt-1 shrink-0 text-ink-faint" aria-hidden />
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words py-0.5">{message.text}</span>
            <div className="flex shrink-0 items-center gap-0.5">
              <button type="button" onClick={() => void queue.guide(message.id)}
                disabled={!running || busy || guiding} title="立即引导当前运行"
                className="flex items-center gap-1 rounded-full px-2 py-1 text-ink-faint transition-colors hover:bg-paper hover:text-ink disabled:opacity-50">
                {busy || guiding ? <Loader2 size={13} className="animate-spin" /> : <CornerDownLeft size={13} />}
                {guiding ? "引导中" : "引导"}
              </button>
              <button type="button" onClick={() => void queue.remove(message.id)}
                disabled={!running || busy} aria-label={`删除待处理追问：${message.text}`}
                title="删除待处理追问"
                className="rounded-full p-1.5 text-ink-faint transition-colors hover:bg-paper hover:text-ink disabled:opacity-50">
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
