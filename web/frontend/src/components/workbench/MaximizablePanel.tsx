"use client";

import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Maximize2, Minimize2 } from "lucide-react";

interface Props {
  title: ReactNode;
  icon?: ReactNode;
  /** Right-aligned header controls (e.g. a tab strip). */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Pad the body. Tables/cards usually want their own padding → false. */
  padded?: boolean;
}

/**
 * A panel with a header and a maximize toggle. When maximized it lifts out
 * of the split layout into a full-screen glass overlay ("zoom one section to
 * see the global view"), then restores back in place.
 *
 * The overlay is rendered through a portal to document.body — ancestors use
 * `backdrop-filter` (.surface), which establishes a containing block for
 * `position: fixed`, so an in-tree overlay would only fill its own panel.
 */
export default function MaximizablePanel({
  title,
  icon,
  actions,
  children,
  className = "",
  padded = false,
}: Props) {
  const [max, setMax] = useState(false);

  const header = (
    <div className="flex items-center gap-2 border-b border-black/5 px-3 py-2">
      {icon && <span className="text-blue-500/80 dark:text-blue-400/80">{icon}</span>}
      <span className="text-xs font-medium tracking-wide text-gray-600">
        {title}
      </span>
      <div className="ml-auto flex items-center gap-1.5">
        {actions}
        <button
          onClick={() => setMax((v) => !v)}
          title={max ? "Restore" : "Maximize"}
          aria-label={max ? "Restore panel" : "Maximize panel"}
          className="rounded p-1 text-gray-400 transition-colors hover:bg-black/5 hover:text-blue-500 dark:hover:bg-white/5 dark:hover:text-blue-400"
        >
          {max ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </button>
      </div>
    </div>
  );

  const inner = (
    <div className="flex h-full min-h-0 flex-col">
      {header}
      <div className={`min-h-0 flex-1 overflow-auto ${padded ? "p-3" : ""}`}>{children}</div>
    </div>
  );

  if (max) {
    return (
      <>
        {/* placeholder keeps the split layout stable while maximized */}
        <div className="flex h-full items-center justify-center text-xs text-gray-400">
          maximized — press ⤢ to restore
        </div>
        {createPortal(
          <div className="overlay-in fixed inset-0 z-[60] bg-white/70 p-3 backdrop-blur-md">
            <div className="surface rise-in h-full w-full overflow-hidden rounded-xl shadow-2xl">
              {inner}
            </div>
          </div>,
          document.body,
        )}
      </>
    );
  }

  return (
    <div className={`flex h-full min-h-0 flex-col overflow-hidden ${className}`}>{inner}</div>
  );
}
