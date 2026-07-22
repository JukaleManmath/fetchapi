"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { IngestForm, JobTracker } from "@/features/ingest/ingest-form";
import type { IngestionJob } from "@/lib/types";

export default function IngestPage() {
  const router = useRouter();
  const [job, setJob] = useState<IngestionJob | null>(null);

  return (
    <div className="relative min-h-full flex flex-col items-center justify-center px-6 py-16 dot-grid">
      {/* Fade-out gradient over the dot grid so edges are clean */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-canvas via-transparent to-canvas" />

      <div className="relative z-10 w-full max-w-2xl animate-fade-up">
        {/* Hero copy */}
        <div className="text-center mb-10">
          <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest mb-3">
            FetchAPI / Ingest
          </p>
          <h1 className="font-display text-4xl font-bold text-ink leading-tight">
            Ingest an OpenAPI spec
          </h1>
          <p className="mt-3 text-sm text-ink-3 leading-relaxed max-w-md mx-auto">
            Upload a file or point to a public URL. FetchAPI parses, validates,
            and indexes it - your AI assistant is ready in seconds.
          </p>
        </div>

        {/* Card */}
        <div className="bg-canvas border border-border-2 rounded-xl shadow-card-lg overflow-hidden">
          {job ? (
            <div className="px-8 py-8">
              <JobTracker
                job={job}
                onReset={() => setJob(null)}
                onView={() => router.push(`/sources/${job.source_id}`)}
              />
            </div>
          ) : (
            <div className="px-8 py-8">
              <IngestForm onJobCreated={setJob} />
            </div>
          )}
        </div>

        {/* Footer note */}
        {!job && (
          <p className="mt-5 text-center text-2xs font-mono text-ink-4">
            Supports OpenAPI 3.0 and 3.1 - JSON or YAML - up to 10 MB
          </p>
        )}
      </div>
    </div>
  );
}
