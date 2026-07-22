import type { Metadata } from "next";
import { KeyRound } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollRevealContainer } from "@/components/ui/scroll-reveal-container";
import { listAuth } from "@/lib/api";
import type { AuthScheme } from "@/lib/types";

interface Props { params: { id: string } }

export const metadata: Metadata = { title: "Auth" };
export const revalidate = 0;

async function getAuth(sourceId: string): Promise<AuthScheme[]> {
  try {
    return await listAuth(sourceId);
  } catch {
    return [];
  }
}

export default async function AuthPage({ params }: Props) {
  const schemes = await getAuth(params.id);

  if (schemes.length === 0) {
    return (
      <EmptyState
        icon={<KeyRound size={28} />}
        title="No auth schemes found"
        description="This source has no active revision, or the spec defines no security schemes."
        className="mt-16"
      />
    );
  }

  return (
    <div className="px-7 py-6 space-y-4">
      <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">
        {schemes.length} scheme{schemes.length !== 1 ? "s" : ""}
      </p>

      <ScrollRevealContainer>
        <ul className="flex flex-col gap-2 stagger" role="list">
          {schemes.map((scheme, i) => (
            <li
              key={scheme.id}
              className="reveal-ready px-4 py-3.5 rounded-md border border-border-1 bg-canvas hover:border-border-3 hover:shadow-card transition-all duration-200"
              style={{ transitionDelay: `${i * 40}ms` }}
            >
              <div className="flex items-center gap-2 mb-1">
                <p className="text-xs font-mono font-semibold text-ink">{scheme.name}</p>
                <Badge variant="inverted">{scheme.scheme_type}</Badge>
              </div>
              {scheme.description && (
                <p className="text-xs text-ink-3 leading-relaxed">{scheme.description}</p>
              )}
            </li>
          ))}
        </ul>
      </ScrollRevealContainer>
    </div>
  );
}
