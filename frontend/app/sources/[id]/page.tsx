"use client";

import { useEffect, useState } from "react";
import { FileCode2, ChevronDown, ChevronRight, KeyRound } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollRevealContainer } from "@/components/ui/scroll-reveal-container";
import { listOperations, getOperation } from "@/lib/api";
import { cn, httpMethodColor } from "@/lib/utils";
import type { Operation } from "@/lib/types";

interface Props { params: { id: string } }

type OperationDetail = Operation & {
  description: string | null;
  security_requirements: Record<string, string[]>[];
  source_pointer: string | null;
};

export default function OperationsPage({ params }: Props) {
  const [operations, setOperations] = useState<Operation[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, OperationDetail>>({});
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    listOperations(params.id)
      .then((r) => setOperations(r.items))
      .catch(() => setOperations([]));
  }, [params.id]);

  async function handleToggle(op: Operation) {
    if (expanded === op.id) {
      setExpanded(null);
      return;
    }
    setExpanded(op.id);
    if (detail[op.id]) return;
    setLoading(op.id);
    try {
      const d = await getOperation(op.id);
      setDetail((prev) => ({ ...prev, [op.id]: d }));
    } finally {
      setLoading(null);
    }
  }

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
    <div className="h-full overflow-y-auto">
    <div className="px-7 py-6 space-y-8">
      <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">
        {operations.length} operation{operations.length !== 1 ? "s" : ""}
      </p>

      {Object.entries(grouped).map(([tag, ops]) => (
        <section key={tag}>
          <h2 className="text-2xs font-mono font-semibold text-ink-4 uppercase tracking-widest mb-3 pb-2 border-b border-border-1">
            {tag}
          </h2>
          <ul className="flex flex-col gap-1.5" role="list">
            {ops.map((op) => {
              const isOpen = expanded === op.id;
              const d = detail[op.id];
              const isLoading = loading === op.id;

              return (
                <li key={op.id} className="rounded-md border border-border-1 bg-canvas overflow-hidden">
                  {/* Row header — clickable */}
                  <button
                    onClick={() => handleToggle(op)}
                    className="w-full flex items-center gap-4 px-4 py-3 hover:bg-surface-2 transition-colors text-left group"
                  >
                    {isOpen
                      ? <ChevronDown size={12} className="text-ink-4 shrink-0" />
                      : <ChevronRight size={12} className="text-ink-4 shrink-0" />
                    }
                    <span className={cn("font-mono text-xs font-bold w-[52px] shrink-0 uppercase", httpMethodColor(op.method))}>
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
                  </button>

                  {/* Expanded detail */}
                  {isOpen && (
                    <div className="border-t border-border-1 px-5 py-4 space-y-3 bg-surface-1">
                      {isLoading && (
                        <p className="text-xs text-ink-4 font-mono animate-pulse">Loading…</p>
                      )}
                      {d && (
                        <>
                          {d.description && (
                            <p className="text-xs text-ink-3 leading-relaxed">{d.description}</p>
                          )}

                          {d.security_requirements && d.security_requirements.length > 0 && (
                            <div className="space-y-1.5">
                              <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest flex items-center gap-1.5">
                                <KeyRound size={10} /> Auth required
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {d.security_requirements.flatMap((req) =>
                                  Object.entries(req).map(([scheme, scopes]) => (
                                    <div key={scheme} className="flex items-center gap-1.5">
                                      <Badge variant="inverted">{scheme}</Badge>
                                      {scopes.map((s) => (
                                        <Badge key={s} variant="muted">{s}</Badge>
                                      ))}
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>
                          )}

                          {d.source_pointer && (
                            <p className="text-2xs font-mono text-ink-4">
                              {d.source_pointer}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
    </div>
  );
}
