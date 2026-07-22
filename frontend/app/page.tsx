import type { Metadata } from "next";
import Link from "next/link";
import { Plus, Database } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SourceCard } from "@/features/sources/source-card";
import { ScrollRevealContainer } from "@/components/ui/scroll-reveal-container";
import { listSources } from "@/lib/api";
import type { Source } from "@/lib/types";

export const metadata: Metadata = { title: "Sources" };
export const revalidate = 0;

async function getSources(): Promise<Source[]> {
  try {
    return await listSources();
  } catch {
    return [];
  }
}

export default async function SourcesPage() {
  const sources = await getSources();

  return (
    <div>
      {/* Dot grid hero band */}
      <div className="dot-grid border-b border-border-1">
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
          className="bg-canvas/80 backdrop-blur-sm"
        />
      </div>

      <div className="px-7 py-6">
        {sources.length === 0 ? (
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
