"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Clock } from "lucide-react";
import Link from "next/link";
import { IngestForm, JobTracker } from "@/features/ingest/ingest-form";
import { getJob, listSources } from "@/lib/api";
import { Button } from "@/components/ui/button";
import type { IngestionJob } from "@/lib/types";

const SESSION_KEY = "fetchapi_active_job";

export default function IngestPage() {
  const router = useRouter();
  const [job, setJob] = useState<IngestionJob | null>(null);
  // null = not checked yet, false = no external job, string = source name ingesting externally
  const [externalIngestion, setExternalIngestion] = useState<string | false | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = sessionStorage.getItem(SESSION_KEY);

    if (stored) {
      // Session has a known job — verify it with the API
      let cached: IngestionJob;
      try {
        cached = JSON.parse(stored) as IngestionJob;
      } catch {
        sessionStorage.removeItem(SESSION_KEY);
        setReady(true);
        return;
      }
      setJob(cached);
      getJob(cached.id)
        .then((j) => {
          if (j.stage === "FAILED") {
            sessionStorage.removeItem(SESSION_KEY);
          } else {
            sessionStorage.setItem(SESSION_KEY, JSON.stringify(j));
          }
          setJob(j);
        })
        .catch(() => {
          sessionStorage.removeItem(SESSION_KEY);
          setJob(null);
        })
        .finally(() => setReady(true));
      return;
    }

    // No session entry — check the API for any source currently ingesting.
    listSources()
      .then((sources) => {
        const inProgress = sources.find(
          (s) => s.ingestion_stage !== null && s.active_revision_id === null
        );
        setExternalIngestion(inProgress ? inProgress.name : false);
      })
      .catch(() => setExternalIngestion(false))
      .finally(() => setReady(true));
  }, []);

  function handleJobCreated(j: IngestionJob) {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(j));
    setJob(j);
    setExternalIngestion(false);
  }

  function handleReset() {
    sessionStorage.removeItem(SESSION_KEY);
    setJob(null);
  }

  const showForm = ready && !job && externalIngestion === false;
  const showExternal = ready && !job && typeof externalIngestion === "string";

  return (
    <div className="relative min-h-full flex flex-col items-center justify-center px-6 py-16 dot-grid">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_50%,transparent_40%,rgba(255,255,255,0.85)_100%)]" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-canvas via-transparent to-canvas" />

      <div className="relative z-10 w-full max-w-xl animate-fade-up">
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

        <div className="bg-canvas border border-border-2 rounded-2xl shadow-card-lg overflow-hidden">
          <div className="px-8 py-8">
            {!ready ? (
              <div className="flex items-center justify-center h-32">
                <span className="w-5 h-5 border-2 border-ink border-t-transparent rounded-full animate-spin" />
              </div>
            ) : job ? (
              <JobTracker
                job={job}
                onReset={handleReset}
                onView={() => router.push(`/sources/${job.source_id}`)}
              />
            ) : showExternal ? (
              <div className="flex flex-col items-center gap-5 py-6 text-center">
                <div className="w-14 h-14 rounded-full border-2 border-border-2 flex items-center justify-center">
                  <Clock size={22} className="text-ink-4 animate-pulse" />
                </div>
                <div className="space-y-1.5">
                  <p className="text-sm font-semibold text-ink">Ingestion in progress</p>
                  <p className="text-xs text-ink-3">
                    <span className="font-mono text-ink-2">{externalIngestion}</span> is currently being ingested.
                    You can start a new ingestion once it completes.
                  </p>
                </div>
                <Link href="/">
                  <Button variant="secondary" size="md">View sources</Button>
                </Link>
              </div>
            ) : showForm ? (
              <IngestForm onJobCreated={handleJobCreated} />
            ) : null}
          </div>
        </div>

        {showForm && (
          <p className="mt-5 text-center text-2xs font-mono text-ink-4">
            Supports OpenAPI 3.0 and 3.1 &middot; JSON or YAML &middot; up to 10 MB
          </p>
        )}
      </div>
    </div>
  );
}
