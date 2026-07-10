"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Braces, ChevronDown, Download, FileArchive, FileSpreadsheet, Loader2, PackageOpen } from "lucide-react";
import { useSettings } from "@/components/settings/SettingsProvider";
import { exportTurnResults, type ResultExportFormat } from "@/lib/resultExport";
import type { Turn } from "@/lib/conversation";

interface Props {
  turn: Turn;
  answer: string;
}

interface ExportOption {
  id: ResultExportFormat;
  label: string;
  detail: string;
  icon: ReactNode;
}

interface MenuPosition {
  left: number;
  width: number;
  maxHeight: number;
  mobile: boolean;
  top?: number;
  bottom?: number;
}

const VIEWPORT_GAP = 8;
const MENU_GAP = 6;
const MENU_WIDTH = 264;
const MENU_HEIGHT = 236;

export default function ResultExportMenu({ turn, answer }: Props) {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState<ResultExportFormat | null>(null);
  const [menuPosition, setMenuPosition] = useState<MenuPosition | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const { notify } = useSettings();
  const tableCount = Object.keys(turn.searchState?.coverage_map.tables ?? {}).filter((id) => !id.startsWith("_")).length || 1;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      if (window.innerWidth < 640) {
        setMenuPosition({
          left: VIEWPORT_GAP,
          bottom: VIEWPORT_GAP,
          width: window.innerWidth - VIEWPORT_GAP * 2,
          maxHeight: Math.min(MENU_HEIGHT, window.innerHeight - VIEWPORT_GAP * 2),
          mobile: true,
        });
        return;
      }

      const rect = trigger.getBoundingClientRect();
      const width = Math.min(MENU_WIDTH, window.innerWidth - VIEWPORT_GAP * 2);
      const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP - VIEWPORT_GAP;
      const spaceAbove = rect.top - MENU_GAP - VIEWPORT_GAP;
      const openAbove = spaceBelow < MENU_HEIGHT && spaceAbove > spaceBelow;
      const available = Math.max(120, openAbove ? spaceAbove : spaceBelow);
      const left = Math.min(
        Math.max(VIEWPORT_GAP, rect.right - width),
        window.innerWidth - width - VIEWPORT_GAP,
      );
      setMenuPosition({
        left,
        width,
        maxHeight: Math.min(MENU_HEIGHT, available),
        top: openAbove ? undefined : rect.bottom + MENU_GAP,
        bottom: openAbove ? window.innerHeight - rect.top + MENU_GAP : undefined,
        mobile: false,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !menuPosition) return;
    if (menuRef.current?.contains(document.activeElement)) return;
    itemRefs.current[0]?.focus();
  }, [menuPosition, open]);

  const options: ExportOption[] = [
    {
      id: "csv",
      label: tableCount > 1 ? "CSV bundle" : "CSV",
      detail: tableCount > 1 ? `${tableCount} tables in a ZIP` : "UTF-8 spreadsheet data",
      icon: <FileSpreadsheet size={15} />,
    },
    {
      id: "xlsx",
      label: "Excel workbook",
      detail: "Tables, relations and metadata",
      icon: <FileSpreadsheet size={15} />,
    },
    {
      id: "json",
      label: "Structured JSON",
      detail: "Rows, schemas and relations",
      icon: <Braces size={15} />,
    },
    {
      id: "package",
      label: "Research package",
      detail: "Answer, evidence, sources and tables",
      icon: <PackageOpen size={15} />,
    },
  ];

  const runExport = async (format: ResultExportFormat) => {
    if (exporting) return;
    setExporting(format);
    try {
      const message = await exportTurnResults({ ...turn, answer }, format);
      notify(message, "success");
      setOpen(false);
      triggerRef.current?.focus();
    } catch (error) {
      notify(`Couldn’t export these results: ${error instanceof Error ? error.message : String(error)}. Try another format or rerun the search.`);
    } finally {
      setExporting(null);
    }
  };

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const items = itemRefs.current.filter((item): item is HTMLButtonElement => !!item && !item.disabled);
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = current < 0 ? 0 : (current + 1) % items.length;
    else if (event.key === "ArrowUp") next = current < 0 ? items.length - 1 : (current - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else if (event.key === "Tab") setOpen(false);
    if (next === null || items.length === 0) return;
    event.preventDefault();
    items[next]?.focus();
  };

  const menuStyle: CSSProperties | undefined = menuPosition ? {
    left: menuPosition.left,
    width: menuPosition.width,
    maxHeight: menuPosition.maxHeight,
    top: menuPosition.top,
    bottom: menuPosition.bottom,
  } : undefined;

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            setOpen(true);
          }
        }}
        disabled={!!exporting}
        aria-label="Export results"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Export results"
        className="flex h-8 items-center gap-1 rounded-md px-2 text-[12px] text-ink-dim transition-colors hover:bg-surface hover:text-ink active:bg-clay disabled:cursor-wait disabled:opacity-60"
      >
        {exporting ? <Loader2 className="animate-spin" size={14} /> : <Download size={14} />}
        <span className="hidden sm:inline">Export</span>
        <ChevronDown size={12} />
      </button>

      {open && menuPosition && createPortal(
        <>
          {menuPosition.mobile && (
            <button type="button" aria-label="Close export menu" onClick={() => setOpen(false)}
              className="fade-in fixed inset-0 z-[109] bg-ink/15 dark:bg-black/40" />
          )}
          <div ref={menuRef} role="menu" aria-label="Export format" style={menuStyle}
            onKeyDown={onMenuKeyDown}
            className={`surface rise-in fixed z-[110] overflow-y-auto rounded-lg p-1 shadow-[0_18px_46px_rgba(15,23,42,0.24)] ${menuPosition.mobile ? "rounded-b-lg" : ""}`}>
          {options.map((option, index) => (
            <button
              key={option.id}
              ref={(element) => { itemRefs.current[index] = element; }}
              type="button"
              role="menuitem"
              onClick={() => void runExport(option.id)}
              disabled={!!exporting}
              className="flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-surface-2 active:bg-clay disabled:opacity-50"
            >
              <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-surface-2 text-accent-ink">
                {exporting === option.id ? <Loader2 className="animate-spin" size={14} /> : option.id === "package" ? <FileArchive size={15} /> : option.icon}
              </span>
              <span className="min-w-0">
                <span className="block text-[12.5px] font-medium text-ink">{option.label}</span>
                <span className="block text-[11px] leading-4 text-ink-faint">{option.detail}</span>
              </span>
            </button>
          ))}
          </div>
        </>,
        document.body,
      )}
    </div>
  );
}
