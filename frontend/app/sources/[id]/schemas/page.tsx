import type { Metadata } from "next";
import { Boxes } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollRevealContainer } from "@/components/ui/scroll-reveal-container";
import { listSchemas } from "@/lib/api";
import type { Schema } from "@/lib/types";

interface Props { params: { id: string } }

export const metadata: Metadata = { title: "Schemas" };
export const revalidate = 0;

async function getSchemas(sourceId: string): Promise<Schema[]> {
  try {
    const result = await listSchemas(sourceId);
    return result.items;
  } catch {
    return [];
  }
}

export default async function SchemasPage({ params }: Props) {
  const schemas = await getSchemas(params.id);

  if (schemas.length === 0) {
    return (
      <EmptyState
        icon={<Boxes size={28} />}
        title="No schemas found"
        description="This source has no active revision, or the spec contains no reusable schemas."
        className="mt-16"
      />
    );
  }

  return (
    <div className="px-7 py-6 space-y-4">
      <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">
        {schemas.length} schema{schemas.length !== 1 ? "s" : ""}
      </p>

      <ScrollRevealContainer>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 stagger" role="list">
          {schemas.map((schema, i) => (
            <li
              key={schema.id}
              className="reveal-ready flex items-start gap-3 px-4 py-3 rounded-md border border-border-1 bg-canvas hover:border-border-3 hover:shadow-card transition-all duration-200"
              style={{ transitionDelay: `${i * 25}ms` }}
            >
              <div className="flex-1 min-w-0">
                <p className="text-xs font-mono font-medium text-ink truncate">{schema.name}</p>
                {schema.description && (
                  <p className="text-xs text-ink-3 mt-0.5 line-clamp-2 leading-relaxed">
                    {schema.description}
                  </p>
                )}
              </div>
              {schema.schema_type && <Badge variant="muted">{schema.schema_type}</Badge>}
            </li>
          ))}
        </ul>
      </ScrollRevealContainer>
    </div>
  );
}
