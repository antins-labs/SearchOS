import { localCopy as copy } from "@/lib/localCopy";
import { File, FileCode2, FileImage, FileJson2, FileSpreadsheet, FileText, Presentation, type LucideIcon } from "lucide-react";

interface FileAppearance {
  Icon: LucideIcon;
  label: string;
  description: string;
  tone: string;
}
const formats: Record<string, FileAppearance> = {
  pdf: { Icon: FileText, label: "PDF", description: copy.formats.pdf, tone: "rose" },
  docx: { Icon: FileText, label: "DOCX", description: copy.formats.word, tone: "blue" },
  pptx: { Icon: Presentation, label: "PPTX", description: copy.formats.slides, tone: "orange" },
  xlsx: { Icon: FileSpreadsheet, label: "XLSX", description: copy.formats.spreadsheet, tone: "green" },
  csv: { Icon: FileSpreadsheet, label: "CSV", description: copy.formats.table, tone: "green" },
  tsv: { Icon: FileSpreadsheet, label: "TSV", description: copy.formats.table, tone: "green" },
  md: { Icon: FileCode2, label: "MD", description: "Markdown", tone: "violet" },
  txt: { Icon: FileText, label: "TXT", description: copy.formats.text, tone: "slate" },
  json: { Icon: FileJson2, label: "JSON", description: copy.formats.structured, tone: "amber" },
  jsonl: { Icon: FileJson2, label: "JSONL", description: copy.formats.structured, tone: "amber" },
  html: { Icon: FileCode2, label: "HTML", description: copy.formats.html, tone: "cyan" },
};
const imageExtensions = new Set(["png", "jpg", "jpeg", "webp", "gif", "svg", "tif", "tiff", "bmp", "heic"]);
const aliases: Record<string, string> = { markdown: "md", text: "txt", word: "docx", doc: "docx", powerpoint: "pptx", ppt: "pptx", excel: "xlsx", xls: "xlsx", htm: "html" };

/** 优先识别原始扩展名；后端的 image / markdown 等类别作为回退。 */
export function fileAppearance(kind?: string, filename = ""): FileAppearance {
  const extension = filename.split(".").pop()?.toLowerCase() ?? "";
  const normalized = (kind ?? "").toLowerCase();
  const raw = formats[extension] || imageExtensions.has(extension) || aliases[extension] ? extension : normalized;
  const key = aliases[raw] ?? raw;
  if (imageExtensions.has(key) || key === "image") return {
    Icon: FileImage, label: key === "image" ? "IMG" : key.toUpperCase(), description: copy.formats.image, tone: "cyan",
  };
  return formats[key] ?? { Icon: File, label: "FILE", description: copy.formats.file, tone: "slate" };
}

export function FileBadge({ kind, filename, small = false }: { kind?: string; filename?: string; small?: boolean }) {
  const { Icon, label, tone } = fileAppearance(kind, filename);
  return <span aria-hidden="true" data-tone={tone} className={`knowledge-file-badge ${small ? "knowledge-file-badge-small" : ""}`}>
    <Icon size={small ? 19 : 23} strokeWidth={1.6} />
    {!small && <span>{label}</span>}
  </span>;
}
