"use client";

import Link from "next/link";
import { ChevronRight, CheckCircle2, Clock } from "lucide-react";
import { useTilt } from "@/lib/hooks/use-tilt";
import { Badge } from "@/components/ui/badge";
import { formatRelativeTime } from "@/lib/utils";
import type { Source } from "@/lib/types";

interface SourceCardProps {
  source: Source;
  index?: number;
}

export function SourceCard({ source, index = 0 }: SourceCardProps) {
  const { ref, onMouseMove, onMouseLeave } = useTilt();
  const isActive = source.active_revision_id !== null;

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className="reveal-ready tilt-card rounded-lg"
      style={{ transitionDelay: `${index * 50}ms` }}
    >
      <Link href={`/sources/${source.id}`} className="block">
        <div className="flex items-center gap-4 px-5 py-4 rounded-lg bg-canvas border border-border-1 shadow-card-sm">
          {/* Status */}
          <div className="shrink-0">
            {isActive ? (
              <CheckCircle2 size={16} className="text-emerald-600" />
            ) : (
              <Clock size={16} className="text-ink-4" />
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-mono font-medium text-ink truncate">
              {source.name}
            </p>
            <p className="text-xs text-ink-4 mt-0.5">
              {formatRelativeTime(source.created_at)}
            </p>
          </div>

          <Badge variant={isActive ? "success" : "muted"}>
            {isActive ? "active" : "pending"}
          </Badge>

          <ChevronRight size={13} className="text-ink-4 shrink-0" />
        </div>
      </Link>
    </div>
  );
}

export function SourceCardSkeleton() {
  return (
    <div className="flex items-center gap-4 px-5 py-4 rounded-lg border border-border-1">
      <div className="w-4 h-4 rounded-full skeleton" />
      <div className="flex-1 space-y-2">
        <div className="h-3.5 w-36 skeleton rounded" />
        <div className="h-2.5 w-20 skeleton rounded" />
      </div>
      <div className="h-5 w-14 skeleton rounded" />
    </div>
  );
}
