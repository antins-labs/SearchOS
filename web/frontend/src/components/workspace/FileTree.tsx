"use client";

import { useState } from "react";
import type { FileNode } from "@/lib/types";
import { ChevronRight, ChevronDown, File, Folder, FolderOpen } from "lucide-react";

interface Props {
  tree: FileNode[];
  onFileSelect: (path: string) => void;
  selectedFile: string | null;
}

export default function FileTree({ tree, onFileSelect, selectedFile }: Props) {
  return (
    <div className="text-sm">
      {tree.map((node) => (
        <TreeNode key={node.path} node={node} onSelect={onFileSelect} selectedPath={selectedFile} depth={0} />
      ))}
    </div>
  );
}

function TreeNode({
  node,
  onSelect,
  selectedPath,
  depth,
}: {
  node: FileNode;
  onSelect: (path: string) => void;
  selectedPath: string | null;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 1);
  const isSelected = node.path === selectedPath;

  if (node.type === "directory") {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className="flex w-full items-center gap-1 px-2 py-1 text-ink-dim hover:bg-surface-2 hover:text-ink"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {open ? <FolderOpen size={14} className="text-accent dark:text-accent" /> : <Folder size={14} className="text-accent dark:text-accent" />}
          <span className="truncate">{node.name}</span>
        </button>
        {open && node.children?.map((child) => (
          <TreeNode key={child.path} node={child} onSelect={onSelect} selectedPath={selectedPath} depth={depth + 1} />
        ))}
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelect(node.path)}
      className={`flex w-full items-center gap-1 px-2 py-1 hover:bg-surface-2 ${
        isSelected ? "bg-blue-50/60 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400" : "text-ink-dim hover:text-ink"
      }`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
    >
      <File size={14} />
      <span className="truncate">{node.name}</span>
      {node.size !== undefined && (
        <span className="ml-auto text-xs text-ink-faint">
          {node.size > 1024 ? `${(node.size / 1024).toFixed(1)}K` : `${node.size}B`}
        </span>
      )}
    </button>
  );
}
