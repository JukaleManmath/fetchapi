"use client";

import { useEffect, useState } from "react";
import { Boxes, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { listSchemas, getSchema } from "@/lib/api";
import type { Schema } from "@/lib/types";

interface Props { params: { id: string } }

type SchemaDetail = { id: string; name: string; description: string | null; schema_json: string };

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function handle() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button onClick={handle} className="flex items-center gap-1 text-2xs font-mono text-ink-4 hover:text-ink transition-colors">
      {copied ? <Check size={10} /> : <Copy size={10} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function SchemasPage({ params }: Props) {
  const [schemas, setSchemas] = useState<Schema[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, SchemaDetail>>({});
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    listSchemas(params.id)
      .then((r) => setSchemas(r.items))
      .catch(() => setSchemas([]));
  }, [params.id]);

  async function handleToggle(schema: Schema) {
    if (expanded === schema.id) {
      setExpanded(null);
      return;
    }
    setExpanded(schema.id);
    if (detail[schema.id]) return;
    setLoading(schema.id);
    try {
      const d = await getSchema(schema.id);
      setDetail((prev) => ({ ...prev, [schema.id]: d }));
    } finally {
      setLoading(null);
    }
  }

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
    <div className="h-full overflow-y-auto">
    <div className="px-7 py-6 space-y-4">
      <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">
        {schemas.length} schema{schemas.length !== 1 ? "s" : ""}
      </p>

      <ul className="flex flex-col gap-1.5" role="list">
        {schemas.map((schema) => {
          const isOpen = expanded === schema.id;
          const d = detail[schema.id];
          const isLoading = loading === schema.id;

          return (
            <li key={schema.id} className="rounded-md border border-border-1 bg-canvas overflow-hidden">
              {/* Row header */}
              <button
                onClick={() => handleToggle(schema)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors text-left group"
              >
                {isOpen
                  ? <ChevronDown size={12} className="text-ink-4 shrink-0" />
                  : <ChevronRight size={12} className="text-ink-4 shrink-0" />
                }
                <span className="font-mono text-xs font-medium text-ink truncate flex-1 group-hover:text-ink transition-colors">
                  {schema.name}
                </span>
                {schema.description && (
                  <span className="text-xs text-ink-4 truncate max-w-[240px] hidden lg:block">
                    {schema.description}
                  </span>
                )}
                {schema.schema_type && <Badge variant="muted">{schema.schema_type}</Badge>}
              </button>

              {/* Expanded JSON Schema */}
              {isOpen && (
                <div className="border-t border-border-1 bg-surface-1">
                  {isLoading && (
                    <p className="px-5 py-4 text-xs text-ink-4 font-mono animate-pulse">Loading…</p>
                  )}
                  {d && (
                    <>
                      {d.description && (
                        <p className="px-5 pt-4 text-xs text-ink-3 leading-relaxed">{d.description}</p>
                      )}
                      <div className="relative">
                        <div className="flex items-center justify-between px-5 pt-3 pb-1">
                          <span className="text-2xs font-mono text-ink-4 uppercase tracking-widest">JSON Schema</span>
                          <CopyButton text={JSON.stringify(JSON.parse(d.schema_json), null, 2)} />
                        </div>
                        <pre className="px-5 pb-4 text-2xs font-mono text-ink-2 leading-relaxed overflow-x-auto max-h-64">
                          {JSON.stringify(JSON.parse(d.schema_json), null, 2)}
                        </pre>
                      </div>
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
    </div>
  );
}
