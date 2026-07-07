"use client";

import { useState, type FormEvent } from "react";
import { Send, Settings2 } from "lucide-react";

interface Props {
  onSubmit: (query: string, opts: { entities?: string[]; attrs?: string[]; type?: string }) => void;
  disabled?: boolean;
}

export default function InputBar({ onSubmit, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [showConfig, setShowConfig] = useState(false);
  const [entities, setEntities] = useState("");
  const [attrs, setAttrs] = useState("");
  const [taskType, setTaskType] = useState("wide");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim() || disabled) return;
    onSubmit(query.trim(), {
      entities: entities ? entities.split(",").map((s) => s.trim()) : undefined,
      attrs: attrs ? attrs.split(",").map((s) => s.trim()) : undefined,
      type: taskType,
    });
    setQuery("");
  };

  return (
    <div className="border-t border-gray-200 bg-gray-50 p-4 dark:border-zinc-800 dark:bg-zinc-900">
      {showConfig && (
        <div className="mb-3 grid grid-cols-3 gap-2 text-sm">
          <input
            className="rounded bg-gray-100 px-3 py-1.5 text-gray-700 placeholder-gray-400 outline-none focus:ring-1 focus:ring-blue-500 dark:bg-zinc-800 dark:text-zinc-300 dark:placeholder-zinc-600"
            placeholder="Entities: Tesla,BYD,NIO"
            value={entities}
            onChange={(e) => setEntities(e.target.value)}
          />
          <input
            className="rounded bg-gray-100 px-3 py-1.5 text-gray-700 placeholder-gray-400 outline-none focus:ring-1 focus:ring-blue-500 dark:bg-zinc-800 dark:text-zinc-300 dark:placeholder-zinc-600"
            placeholder="Attributes: revenue,employees"
            value={attrs}
            onChange={(e) => setAttrs(e.target.value)}
          />
          <select
            className="rounded bg-gray-100 px-3 py-1.5 text-gray-700 outline-none dark:bg-zinc-800 dark:text-zinc-300"
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
          >
            <option value="wide">Wide Search</option>
            <option value="deep">Deep Search</option>
            <option value="local">Local Search</option>
          </select>
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setShowConfig(!showConfig)}
          className="rounded p-2 text-gray-400 hover:bg-gray-200 hover:text-gray-700 dark:text-zinc-500 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          title="Search config"
        >
          <Settings2 size={18} />
        </button>
        <input
          className="flex-1 rounded-lg bg-gray-100 px-4 py-2.5 text-gray-800 placeholder-gray-400 outline-none focus:ring-1 focus:ring-blue-500 dark:bg-zinc-800 dark:text-zinc-200 dark:placeholder-zinc-500"
          placeholder="Ask a question or search for information..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
        />
        <button
          type="submit"
          disabled={disabled || !query.trim()}
          className="rounded-lg bg-gray-200 p-2.5 text-gray-600 disabled:opacity-30 hover:bg-gray-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
