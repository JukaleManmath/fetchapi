"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/types";

interface Props {
  citations: Citation[];
}

export function RetrievalInspector({ citations }: Props) {
  const [open, setOpen] = useState(false);

  if (citations.length === 0) return null;

  return (
    <div className="border border-border-1 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-ink-3 hover:text-ink hover:bg-surface-2 transition-colors"
      >
        <span className="flex items-center gap-2 font-mono">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          Retrieval inspector
          <span className="text-ink-4">· {citations.length} retrieved chunk{citations.length !== 1 ? "s" : ""}</span>
        </span>
      </button>

      {open && (
        <div className="border-t border-border-1 divide-y divide-border-1">
          {citations.map((c, i) => (
            <div key={c.chunk_id} className="px-4 py-3 space-y-1.5 bg-canvas">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-2xs text-ink-4">[S{i + 1}]</span>
                <Badge variant="muted">{c.entity_type}</Badge>
                {c.method && (
                  <span className="font-mono text-2xs font-bold text-ink-3 uppercase">
                    {c.method}
                  </span>
                )}
                {c.path && (
                  <span className="font-mono text-2xs text-ink-3 truncate max-w-[200px]">
                    {c.path}
                  </span>
                )}
                <span className="ml-auto font-mono text-2xs text-ink-4">{c.title}</span>
              </div>

              {/* Scores */}
              <div className="flex items-center gap-4">
                {c.reranker_score != null && (
                  <ScoreBar label="reranker" value={c.reranker_score} max={1} color="emerald" />
                )}
              </div>

              {/* Chunk text excerpt */}
              {c.chunk_text && (
                <p className="text-2xs text-ink-4 leading-relaxed line-clamp-3 font-mono">
                  {c.chunk_text}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScoreBar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: "emerald" | "blue" | "violet";
}) {
  const pct = Math.min(Math.max(value / max, 0), 1) * 100;
  const barColor = {
    emerald: "bg-emerald-500",
    blue: "bg-blue-500",
    violet: "bg-violet-500",
  }[color];

  return (
    <div className="flex items-center gap-2">
      <span className="text-2xs font-mono text-ink-4 w-16 shrink-0">{label}</span>
      <div className="w-24 h-1 bg-surface-2 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-2xs font-mono text-ink-4">{value.toFixed(3)}</span>
    </div>
  );
}
