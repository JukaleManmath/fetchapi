"use client";

import { useState, useEffect } from "react";
import { Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { OperationPicker } from "@/features/generate/operation-picker";
import { LanguageSelector } from "@/features/generate/language-selector";
import { CodeBlock } from "@/features/generate/code-block";
import { ValidationReport } from "@/features/generate/validation-report";
import { listOperations, generateIntegration } from "@/lib/api";
import type { Operation, GenerationResult } from "@/lib/types";

interface Props { params: { id: string } }

export default function GeneratePage({ params }: Props) {
  const [operations, setOperations] = useState<Operation[]>([]);
  const [selected, setSelected] = useState<Operation | null>(null);
  const [language, setLanguage] = useState<"python" | "typescript" | "java">("python");
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listOperations(params.id)
      .then((r) => setOperations(r.items))
      .catch(() => setOperations([]));
  }, [params.id]);

  async function handleGenerate() {
    if (!selected) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await generateIntegration(selected.id, language);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
    <div className="px-8 py-8 space-y-8 w-full max-w-4xl">
      <div className="space-y-2">
        <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Generate</p>
        <h2 className="text-xl font-semibold text-ink">Integration code</h2>
        <p className="text-sm text-ink-3">Select an operation and language to generate working integration code backed by the spec.</p>
      </div>

      {operations.length === 0 ? (
        <EmptyState
          icon={<Code2 size={24} />}
          title="No operations available"
          description="This source has no active revision with indexable operations."
        />
      ) : (
        <>
          <div className="space-y-3">
            <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Operation</p>
            <OperationPicker
              operations={operations}
              selected={selected}
              onSelect={setSelected}
            />
          </div>

          <div className="space-y-3">
            <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Language</p>
            <LanguageSelector selected={language} onSelect={setLanguage} />
          </div>

          <Button
            size="sm"
            disabled={!selected || loading}
            onClick={handleGenerate}
          >
            {loading ? "Generating…" : "Generate"}
          </Button>

          {error && (
            <p className="text-xs text-red-500 font-mono">{error}</p>
          )}

          {result && (
            <div className="space-y-4">
              <CodeBlock code={result.code} language={result.language} />
              <div className="space-y-2">
                <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Validation</p>
                <ValidationReport
                  contractIssues={result.contract_issues}
                  syntaxIssues={result.syntax_issues}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
    </div>
  );
}
