"use client";

import type { ReactNode } from "react";

/** Section scaffold: serif heading + one-line description + card body. */
export function SectionShell({
  id, title, description, children,
}: {
  id?: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-6">
      <h2 className="font-serif text-[17px] text-ink">{title}</h2>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">{description}</p>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

/** A titled sub-block inside a section (e.g. Providers / Models / Roles). */
export function SubSection({
  title, description, children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[14px] font-medium text-ink">{title}</h3>
        {description && (
          <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-faint">{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}

/** A bordered card grouping related rows. */
export function Card({ children }: { children: ReactNode }) {
  return <div className="surface divide-y divide-line rounded-xl">{children}</div>;
}

/** One label-left / control-right row inside a Card. */
export function Row({
  label, hint, children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <div className="min-w-0">
        <div className="text-[13.5px] text-ink">{label}</div>
        {hint && <div className="mt-0.5 text-[12px] text-ink-faint">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/** Offline placeholder rows shown while settings can't be loaded. */
export function OfflineSkeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-11 animate-pulse rounded-lg bg-surface-2" />
      ))}
    </div>
  );
}
