import type { Metadata } from "next";
import { FileCode2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollRevealContainer } from "@/components/ui/scroll-reveal-container";
import { listOperations } from "@/lib/api";
import { cn, httpMethodColor } from "@/lib/utils";
import type { Operation } from "@/lib/types";

interface Props { params: { id: string } }

export const metadata: Metadata = { title: "Operations" };
export const revalidate = 0;

async function getOperations(sourceId: string): Promise<Operation[]> {
  try {
    const result = await listOperations(sourceId);
    return result.items;
  } catch {
    return [];
  }
}

export default async function OperationsPage({ params }: Props) {
  const operations = await getOperations(params.id);

  if (operations.length === 0) {
    return (
      <EmptyState
        icon={<FileCode2 size={28} />}
        title="No operations found"
        description="This source has no active revision, or the spec contains no operations."
        className="mt-16"
      />
    );
  }

  const grouped = operations.reduce<Record<string, Operation[]>>((acc, op) => {
    const tag = op.tags[0] ?? "Untagged";
    (acc[tag] ??= []).push(op);
    return acc;
  }, {});

  return (
    <div className="px-7 py-6 space-y-8">
      <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">
        {operations.length} operation{operations.length !== 1 ? "s" : ""}
      </p>

      {Object.entries(grouped).map(([tag, ops]) => (
        <section key={tag}>
          <h2 className="text-2xs font-mono font-semibold text-ink-4 uppercase tracking-widest mb-3 pb-2 border-b border-border-1">
            {tag}
          </h2>
          <ScrollRevealContainer>
            <ul className="flex flex-col gap-1.5 stagger" role="list">
              {ops.map((op, i) => (
                <li
                  key={op.id}
                  className="reveal-ready flex items-center gap-4 px-4 py-3 rounded-md border border-border-1 bg-canvas hover:border-border-3 hover:shadow-card transition-all duration-200 cursor-pointer group"
                  style={{ transitionDelay: `${i * 30}ms` }}
                >
                  <span
                    className={cn(
                      "font-mono text-xs font-bold w-[52px] shrink-0 uppercase",
                      httpMethodColor(op.method)
                    )}
                  >
                    {op.method}
                  </span>
                  <span className="font-mono text-xs text-ink-2 truncate flex-1 group-hover:text-ink transition-colors">
                    {op.path}
                  </span>
                  {op.summary && (
                    <span className="text-xs text-ink-4 truncate max-w-[240px] hidden lg:block">
                      {op.summary}
                    </span>
                  )}
                  {op.deprecated && <Badge variant="warning">deprecated</Badge>}
                </li>
              ))}
            </ul>
          </ScrollRevealContainer>
        </section>
      ))}
    </div>
  );
}
