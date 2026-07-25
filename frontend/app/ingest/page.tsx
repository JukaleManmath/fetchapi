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
      {/* Radial fade: bright center, dots fade at edges */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_50%,transparent_40%,rgba(255,255,255,0.85)_100%)]" />
      {/* Top and bottom hard fade so the header/footer feel grounded */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-canvas via-transparent to-canvas" />

      <div className="relative z-10 w-full max-w-xl animate-fade-up">
        {/* Hero */}
        <div className="text-center mb-10 space-y-3">
          <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">
            FetchAPI / Ingest
          </p>
          <h1 className="text-4xl font-bold text-ink leading-tight tracking-tight">
            Ingest an OpenAPI spec
          </h1>
          <p className="text-sm text-ink-3 leading-relaxed max-w-sm mx-auto">
            Upload a file or point to a public URL. FetchAPI parses, validates,
            and indexes it so your AI assistant is ready in seconds.
          </p>
        </div>

        {/* Card */}
        <div className="bg-canvas border border-border-2 rounded-2xl shadow-card-lg overflow-hidden">
          <div className="px-8 py-8">
            {job ? (
              <JobTracker
                job={job}
                onReset={() => setJob(null)}
                onView={() => router.push(`/sources/${job.source_id}`)}
              />
            ) : (
              <IngestForm onJobCreated={setJob} />
            )}
          </div>
        </div>

        {/* Footer note */}
        {!job && (
          <p className="mt-5 text-center text-2xs font-mono text-ink-4">
            Supports OpenAPI 3.0 and 3.1 &middot; JSON or YAML &middot; up to 10 MB
          </p>
        )}
      </div>
    </div>
  );
}
