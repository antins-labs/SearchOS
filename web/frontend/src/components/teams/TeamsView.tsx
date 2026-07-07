"use client";

import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import type { WSEvent } from "@/lib/types";
import WorkerPane from "./WorkerPane";

interface WorkerInfo {
  name: string;
  intent: string;
  scope: string;
  status: "pending" | "running" | "completed" | "error";
  events: WSEvent[];
}

interface Props {
  workers: WorkerInfo[];
}

export default function TeamsView({ workers }: Props) {
  if (workers.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-400 dark:text-zinc-600">
        Workers will appear here when the search starts.
      </div>
    );
  }

  // Arrange workers in a grid: up to 2 columns
  const cols = workers.length <= 2 ? workers.length : 2;
  const rows = Math.ceil(workers.length / cols);

  return (
    <PanelGroup direction="vertical" className="h-full">
      {Array.from({ length: rows }).map((_, rowIdx) => {
        const rowWorkers = workers.slice(rowIdx * cols, (rowIdx + 1) * cols);
        return (
          <div key={rowIdx}>
            {rowIdx > 0 && <PanelResizeHandle className="h-1 bg-gray-200 hover:bg-gray-300 dark:bg-zinc-800 dark:hover:bg-zinc-700 cursor-row-resize" />}
            <Panel minSize={20}>
              <PanelGroup direction="horizontal">
                {rowWorkers.map((w, colIdx) => (
                  <div key={w.name} className="contents">
                    {colIdx > 0 && <PanelResizeHandle className="w-1 bg-gray-200 hover:bg-gray-300 dark:bg-zinc-800 dark:hover:bg-zinc-700 cursor-col-resize" />}
                    <Panel minSize={20}>
                      <WorkerPane {...w} />
                    </Panel>
                  </div>
                ))}
              </PanelGroup>
            </Panel>
          </div>
        );
      })}
    </PanelGroup>
  );
}
