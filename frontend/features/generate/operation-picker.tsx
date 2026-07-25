"use client";
import { useState } from "react";
import { cn, httpMethodColor } from "@/lib/utils";
import type { Operation } from "@/lib/types";

interface Props {
  operations: Operation[];
  selected: Operation | null;
  onSelect: (op: Operation) => void;
}

export function OperationPicker({ operations, selected, onSelect }: Props) {
  const [search, setSearch] = useState("");

  const filtered = operations.filter((op) => {
    const q = search.toLowerCase();
    return (
      op.path.toLowerCase().includes(q) ||
      op.method.toLowerCase().includes(q) ||
      (op.summary ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex flex-col gap-2">
      <input
        type="text"
        placeholder="Search operations…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full px-3 py-2 text-sm bg-canvas border border-border-2 rounded-md outline-none focus:border-border-3 text-ink placeholder:text-ink-4 font-mono"
      />
      <ul className="flex flex-col gap-1 max-h-56 overflow-y-auto pr-1">
        {filtered.map((op) => (
          <li key={op.id}>
            <button
              onClick={() => onSelect(op)}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 rounded-md border text-left transition-all duration-150",
                selected?.id === op.id
                  ? "border-ink bg-ink text-canvas"
                  : "border-border-1 bg-canvas hover:border-border-3 text-ink"
              )}
            >
              <span className={cn(
                "font-mono text-xs font-bold w-[52px] shrink-0 uppercase",
                selected?.id === op.id ? "text-canvas" : httpMethodColor(op.method)
              )}>
                {op.method}
              </span>
              <span className="font-mono text-xs truncate flex-1">{op.path}</span>
              {op.summary && (
                <span className="text-xs text-ink-4 truncate max-w-[160px] hidden md:block">
                  {op.summary}
                </span>
              )}
            </button>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="px-3 py-4 text-xs text-ink-4 text-center">No operations match</li>
        )}
      </ul>
    </div>
  );
}
