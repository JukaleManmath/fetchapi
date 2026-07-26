"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, CheckCircle2, Clock, AlertCircle, Trash2 } from "lucide-react";
import { useTilt } from "@/lib/hooks/use-tilt";
import { Badge } from "@/components/ui/badge";
import { formatRelativeTime } from "@/lib/utils";
import { deleteSource, getSource } from "@/lib/api";
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
  onDelete?: () => void;
}

export function SourceCard({ source: initialSource, index = 0, onDelete }: SourceCardProps) {
  const { ref, onMouseMove, onMouseLeave } = useTilt();
  const [source, setSource] = useState(initialSource);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const isActive = source.active_revision_id !== null;
  const isFailed = source.ingestion_stage === "failed";
  const isBuilding = !isActive && !isFailed;

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDeleting(true);
    try {
      await deleteSource(source.id);
      onDelete?.();
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

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
      <div className="flex items-center gap-2 rounded-lg bg-canvas border border-border-1 shadow-card-sm pr-3">
        <Link href={`/sources/${source.id}`} className="flex-1 min-w-0">
          <div className="flex items-center gap-4 px-5 py-4">
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

        {/* Delete control */}
        {confirmDelete ? (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-xs text-red-500 hover:text-red-600 px-2 py-1 rounded disabled:opacity-50"
            >
              {deleting ? "…" : "Yes"}
            </button>
            <button
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setConfirmDelete(false); }}
              className="text-xs text-ink-4 hover:text-ink px-2 py-1 rounded"
            >
              No
            </button>
          </div>
        ) : (
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setConfirmDelete(true); }}
            className="shrink-0 text-ink-4 hover:text-red-500 p-1 rounded transition-colors"
            aria-label="Delete source"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
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
