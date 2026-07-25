"use client";
import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/types";

interface Props { citation: Citation; index: number }

export function CitationCard({ citation, index }: Props) {
  return (
    <div className="flex gap-2.5 px-3 py-2.5 rounded-md border border-border-1 bg-surface text-xs">
      <span className="font-mono text-ink-4 shrink-0">[S{index + 1}]</span>
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-1.5">
          <Badge variant="muted">{citation.entity_type}</Badge>
          <span className="font-mono text-ink-4 text-2xs">
            score {citation.score.toFixed(3)}
          </span>
        </div>
        <p className="text-ink-3 leading-relaxed line-clamp-3">{citation.chunk_text}</p>
      </div>
    </div>
  );
}
