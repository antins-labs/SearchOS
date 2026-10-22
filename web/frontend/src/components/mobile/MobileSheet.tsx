"use client";

import { useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import useDialogFocus from "@/hooks/useDialogFocus";
import s from "./mobile-assistant.module.css";

export default function MobileSheet({ title, subtitle, onClose, children, footer, reader = false }: {
  title: string; subtitle?: string; onClose: () => void; children: ReactNode; footer?: ReactNode; reader?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialogFocus({ containerRef: ref, initialFocusRef: closeRef, onClose });
  return <div className={s.overlay}>
    <section ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={`${s.sheet} ${reader ? s.readerSheet : ""}`}>
      <header className={s.sheetHeader}><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button ref={closeRef} className={s.iconButton} onClick={onClose} aria-label={`关闭${title}`}><X size={21} /></button></header>
      <div className={s.sheetBody}>{children}</div>
      {footer && <footer className={s.sheetFooter}>{footer}</footer>}
    </section>
  </div>;
}
