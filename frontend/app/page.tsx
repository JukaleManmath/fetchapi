"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Database } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SourceCard, SourceCardSkeleton } from "@/features/sources/source-card";
import { ScrollRevealContainer } from "@/components/ui/scroll-reveal-container";
import { listSources } from "@/lib/api";
import type { Source } from "@/lib/types";

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listSources()
      .then(setSources)
      .catch(() => setSources([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-full dot-grid">
      <div className="bg-canvas border-b border-border-1">
        <PageHeader
          title="Sources"
          description="Ingested OpenAPI specs available for querying through MCP and HTTP."
          action={
            <Link href="/ingest">
              <Button size="sm">
                <Plus size={13} />
                Ingest spec
              </Button>
            </Link>
          }
        />
      </div>

      <div className="px-7 py-6">
        {loading ? (
          <ul className="flex flex-col gap-2.5">
            {[0, 1, 2].map((i) => (
              <li key={i}><SourceCardSkeleton /></li>
            ))}
          </ul>
        ) : sources.length === 0 ? (
          <EmptyState
            icon={<Database size={28} />}
            title="No sources yet"
            description="Upload an OpenAPI 3.0 or 3.1 spec to get structured, citation-backed knowledge in your AI assistant."
            action={
              <Link href="/ingest">
                <Button size="sm">
                  <Plus size={13} />
                  Ingest your first spec
                </Button>
              </Link>
            }
          />
        ) : (
          <>
            <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest mb-4">
              {sources.length} source{sources.length !== 1 ? "s" : ""}
            </p>
            <ScrollRevealContainer>
              <ul className="flex flex-col gap-2.5 stagger" role="list">
                {sources.map((source, i) => (
                  <li key={source.id}>
                    <SourceCard source={source} index={i} />
                  </li>
                ))}
              </ul>
            </ScrollRevealContainer>
          </>
        )}
      </div>
    </div>
  );
}
