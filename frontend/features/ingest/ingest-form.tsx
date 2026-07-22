"use client";

import { useState, useRef, type ChangeEvent, type FormEvent } from "react";
import { Upload, Link2, CheckCircle2, AlertCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ingestFromFile, ingestFromUrl } from "@/lib/api";
import type { IngestionJob } from "@/lib/types";

type Mode = "url" | "file";

interface IngestFormProps {
  onJobCreated: (job: IngestionJob) => void;
}

export function IngestForm({ onJobCreated }: IngestFormProps) {
  const [mode, setMode] = useState<Mode>("url");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    if (f && !name) setName(f.name.replace(/\.(yaml|yml|json)$/i, ""));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    setFile(f);
    if (!name) setName(f.name.replace(/\.(yaml|yml|json)$/i, ""));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let job: IngestionJob;
      if (mode === "url") {
        if (!url) throw new Error("URL is required");
        job = await ingestFromUrl(name || url, url);
      } else {
        if (!file) throw new Error("Please select a file");
        job = await ingestFromFile(name || file.name, file);
      }
      onJobCreated(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Mode toggle */}
      <div className="flex gap-px p-1 bg-surface-2 rounded-lg border border-border-1 w-full">
        {(["url", "file"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-all duration-150 cursor-pointer",
              mode === m
                ? "bg-canvas text-ink shadow-card-sm border border-border-1"
                : "text-ink-3 hover:text-ink"
            )}
          >
            {m === "url" ? <Link2 size={14} /> : <Upload size={14} />}
            {m === "url" ? "From URL" : "Upload file"}
          </button>
        ))}
      </div>

      {/* Source name */}
      <Input
        label="Source name"
        placeholder="e.g. Stripe API, GitHub REST API"
        value={name}
        onChange={(e) => setName(e.target.value)}
        helperText="How this source will appear in your assistant"
      />

      {/* URL or file drop */}
      {mode === "url" ? (
        <Input
          label="OpenAPI spec URL"
          type="url"
          placeholder="https://petstore3.swagger.io/api/v3/openapi.json"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          helperText="Publicly accessible OpenAPI 3.0 or 3.1 - JSON or YAML"
        />
      ) : (
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-ink-2 uppercase tracking-wider">
            OpenAPI spec file
          </label>
          <div
            onClick={() => fileRef.current?.click()}
            onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            role="button"
            tabIndex={0}
            aria-label="OpenAPI spec file drop zone"
            className={cn(
              "flex flex-col items-center justify-center gap-3 h-40 rounded-lg border-2 border-dashed",
              "transition-all duration-150 cursor-pointer",
              dragging
                ? "border-ink bg-surface-2 scale-[1.01]"
                : file
                ? "border-emerald-400 bg-emerald-50"
                : "border-border-2 hover:border-border-3 hover:bg-surface-1"
            )}
          >
            {file ? (
              <>
                <CheckCircle2 size={22} className="text-emerald-600" />
                <div className="text-center">
                  <p className="text-sm font-mono font-medium text-ink">{file.name}</p>
                  <p className="text-xs text-ink-4 mt-0.5">
                    {(file.size / 1024).toFixed(1)} KB - click to change
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="w-10 h-10 rounded-lg border border-border-2 flex items-center justify-center bg-surface-1">
                  <Upload size={18} className="text-ink-3" />
                </div>
                <div className="text-center">
                  <p className="text-sm text-ink">Drop your spec here</p>
                  <p className="text-xs text-ink-4 mt-0.5">.yaml, .yml, or .json</p>
                </div>
              </>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".yaml,.yml,.json"
            onChange={handleFileChange}
            className="sr-only"
            aria-label="OpenAPI spec file"
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          className="flex items-start gap-2.5 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3"
          role="alert"
        >
          <AlertCircle size={15} className="shrink-0 mt-0.5" />
          <span className="text-xs">{error}</span>
        </div>
      )}

      <Button type="submit" loading={loading} size="lg" className="w-full">
        {loading ? "Starting ingestion..." : (
          <>
            Ingest spec
            <ArrowRight size={15} />
          </>
        )}
      </Button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Job tracker
// ---------------------------------------------------------------------------

const STAGES = [
  "QUEUED",
  "FETCHING",
  "SNAPSHOTTING",
  "PARSING",
  "VALIDATING",
  "NORMALIZING",
  "ACTIVE",
] as const;

interface JobTrackerProps {
  job: IngestionJob;
  onReset: () => void;
  onView: () => void;
}

export function JobTracker({ job, onReset, onView }: JobTrackerProps) {
  const currentIndex = STAGES.indexOf(job.stage as (typeof STAGES)[number]);
  const isFailed = job.stage === "FAILED";
  const isDone = job.stage === "ACTIVE";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="text-center">
        {isDone ? (
          <>
            <div className="w-14 h-14 rounded-full border-2 border-emerald-200 bg-emerald-50 flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 size={26} className="text-emerald-600" />
            </div>
            <h2 className="font-display text-2xl font-bold text-ink">Ready</h2>
            <p className="text-sm text-ink-3 mt-1">
              Your spec has been indexed and is ready to query.
            </p>
          </>
        ) : isFailed ? (
          <>
            <div className="w-14 h-14 rounded-full border-2 border-red-200 bg-red-50 flex items-center justify-center mx-auto mb-4">
              <AlertCircle size={26} className="text-red-600" />
            </div>
            <h2 className="font-display text-2xl font-bold text-ink">Ingestion failed</h2>
            <p className="text-sm text-ink-3 mt-1">{job.error_message ?? "An error occurred."}</p>
          </>
        ) : (
          <>
            <div className="w-14 h-14 rounded-full border-2 border-border-2 flex items-center justify-center mx-auto mb-4">
              <span className="w-5 h-5 border-2 border-ink border-t-transparent rounded-full animate-spin" />
            </div>
            <h2 className="font-display text-2xl font-bold text-ink">Ingesting...</h2>
            <p className="text-xs font-mono text-ink-4 mt-1">{job.id.slice(0, 16)}...</p>
          </>
        )}
      </div>

      {/* Pipeline */}
      <ol className="relative space-y-0" aria-label="Ingestion pipeline stages">
        {STAGES.map((stage, i) => {
          const done = currentIndex > i;
          const active = currentIndex === i && !isFailed;
          const pending = currentIndex < i || isFailed;
          const isLast = i === STAGES.length - 1;

          return (
            <li key={stage} className="flex gap-4">
              {/* Connector column */}
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "w-3 h-3 rounded-full border-2 shrink-0 transition-all duration-300 mt-0.5",
                    done  && "bg-ink border-ink",
                    active && "bg-canvas border-ink shadow-ink-glow",
                    pending && "bg-canvas border-border-2"
                  )}
                  aria-hidden="true"
                />
                {!isLast && (
                  <div
                    className={cn(
                      "w-px flex-1 mt-1 mb-1 min-h-[20px] transition-colors duration-300",
                      done ? "bg-ink" : "bg-border-1"
                    )}
                  />
                )}
              </div>

              {/* Label */}
              <div className={cn("pb-4", isLast && "pb-0")}>
                <span
                  className={cn(
                    "text-xs font-mono transition-colors duration-150",
                    done    && "text-ink",
                    active  && "text-ink font-semibold",
                    pending && "text-ink-4"
                  )}
                >
                  {stage}
                </span>
                {active && (
                  <p className="text-xs text-ink-4 mt-0.5">In progress...</p>
                )}
                {done && stage === "ACTIVE" && (
                  <p className="text-xs text-emerald-600 mt-0.5">Complete</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {/* Actions */}
      <div className="flex flex-col gap-2.5">
        {isDone && (
          <Button size="lg" className="w-full" onClick={onView}>
            View source <ArrowRight size={15} />
          </Button>
        )}
        {(isFailed || isDone) && (
          <Button variant="secondary" size="md" className="w-full" onClick={onReset}>
            Ingest another spec
          </Button>
        )}
      </div>
    </div>
  );
}
