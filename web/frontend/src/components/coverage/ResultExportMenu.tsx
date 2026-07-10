"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
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

export default function ResultExportMenu({ turn, answer }: Props) {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState<ResultExportFormat | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const { notify } = useSettings();
  const tableCount = Object.keys(turn.searchState?.coverage_map.tables ?? {}).filter((id) => !id.startsWith("_")).length || 1;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

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
    } catch (error) {
      notify(`Couldn’t export these results: ${error instanceof Error ? error.message : String(error)}. Try another format or rerun the search.`);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
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

      {open && (
        <div role="menu" aria-label="Export format" className="surface rise-in absolute right-0 top-full z-30 mt-1 w-[248px] overflow-hidden rounded-lg p-1 shadow-xl">
          {options.map((option) => (
            <button
              key={option.id}
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
      )}
    </div>
  );
}
