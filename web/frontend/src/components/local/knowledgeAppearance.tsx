import { File, FileCode2, FileImage, FileJson2, FileSpreadsheet, FileText, Presentation, type LucideIcon } from "lucide-react";

interface FileAppearance {
  Icon: LucideIcon;
  label: string;
  description: string;
  tone: string;
}
const formats: Record<string, FileAppearance> = {
  pdf: { Icon: FileText, label: "PDF", description: "PDF 文档", tone: "rose" },
  docx: { Icon: FileText, label: "DOCX", description: "Word 文档", tone: "blue" },
  pptx: { Icon: Presentation, label: "PPTX", description: "演示文稿", tone: "orange" },
  xlsx: { Icon: FileSpreadsheet, label: "XLSX", description: "电子表格", tone: "green" },
  csv: { Icon: FileSpreadsheet, label: "CSV", description: "数据表格", tone: "green" },
  tsv: { Icon: FileSpreadsheet, label: "TSV", description: "数据表格", tone: "green" },
  md: { Icon: FileCode2, label: "MD", description: "Markdown", tone: "violet" },
  txt: { Icon: FileText, label: "TXT", description: "纯文本", tone: "slate" },
  json: { Icon: FileJson2, label: "JSON", description: "结构化数据", tone: "amber" },
  jsonl: { Icon: FileJson2, label: "JSONL", description: "结构化数据", tone: "amber" },
  html: { Icon: FileCode2, label: "HTML", description: "网页文档", tone: "cyan" },
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
    Icon: FileImage, label: key === "image" ? "IMG" : key.toUpperCase(), description: "图片", tone: "cyan",
  };
  return formats[key] ?? { Icon: File, label: "FILE", description: "文件", tone: "slate" };
}

export function FileBadge({ kind, filename, small = false }: { kind?: string; filename?: string; small?: boolean }) {
  const { Icon, label, tone } = fileAppearance(kind, filename);
  return <span aria-hidden="true" data-tone={tone} className={`knowledge-file-badge ${small ? "knowledge-file-badge-small" : ""}`}>
    <Icon size={small ? 19 : 23} strokeWidth={1.6} />
    {!small && <span>{label}</span>}
  </span>;
}
