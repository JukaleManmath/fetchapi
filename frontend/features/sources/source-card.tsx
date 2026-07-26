"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { useTilt } from "@/lib/hooks/use-tilt";
import { Badge } from "@/components/ui/badge";
import { formatRelativeTime } from "@/lib/utils";
import { getSource } from "@/lib/api";
import type { Source } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  queued: "queued",
  fetching: "fetching",
  snapshotting: "snapshotting",
  parsing: "parsing",
  validating: "validating",
  normalizing: "normalizing",
  chunking: "chunking",
  embedding: "embedding",
  indexing: "indexing",
  verifying: "verifying",
  failed: "failed",
};

interface SourceCardProps {
  source: Source;
  index?: number;
}

export function SourceCard({ source: initialSource, index = 0 }: SourceCardProps) {
  const { ref, onMouseMove, onMouseLeave } = useTilt();
  const [source, setSource] = useState(initialSource);

  const isActive = source.active_revision_id !== null;
  const isFailed = source.ingestion_stage === "failed";
  const isBuilding = !isActive && !isFailed;

  // Poll every 4s while ingesting
  useEffect(() => {
    if (!isBuilding) return;
    const interval = setInterval(async () => {
      try {
        const updated = await getSource(source.id);
        setSource(updated);
      } catch {
        // ignore transient errors
      }
    }, 8000);
    return () => clearInterval(interval);
  }, [isBuilding, source.id]);

  const stageLabel = source.ingestion_stage
    ? (STAGE_LABELS[source.ingestion_stage.toLowerCase()] ?? source.ingestion_stage.toLowerCase())
    : null;

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
          {/* Status icon */}
          <div className="shrink-0">
            {isActive ? (
              <CheckCircle2 size={16} className="text-emerald-600" />
            ) : isFailed ? (
              <AlertCircle size={16} className="text-red-500" />
            ) : (
              <Clock size={16} className="text-ink-4 animate-pulse" />
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

          {/* Stage badge */}
          {isActive ? (
            <Badge variant="success">active</Badge>
          ) : isFailed ? (
            <Badge variant="error">failed</Badge>
          ) : (
            <Badge variant="muted">
              {stageLabel ?? "pending"}
            </Badge>
          )}

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
