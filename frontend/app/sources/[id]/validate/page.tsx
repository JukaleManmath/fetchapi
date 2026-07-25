"use client";

import { useState } from "react";
import { CurlInput } from "@/features/validate/curl-input";
import { FindingsList } from "@/features/validate/findings-list";
import { MatchedOperation } from "@/features/validate/matched-operation";
import { CorrectedCurl } from "@/features/validate/corrected-curl";
import { validateCurl } from "@/lib/api";
import type { ValidationResult } from "@/lib/types";

interface Props { params: { id: string } }

export default function ValidatePage({ params }: Props) {
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleValidate(curl: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await validateCurl(params.id, curl);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
    <div className="px-8 py-8 space-y-8 w-full max-w-4xl">
      <div className="space-y-2">
        <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Validate</p>
        <h2 className="text-xl font-semibold text-ink">Request debugger</h2>
        <p className="text-sm text-ink-3">Paste a curl command to validate it against the spec. Get findings and a corrected example.</p>
      </div>

      <CurlInput onValidate={handleValidate} loading={loading} />

      {error && <p className="text-xs text-red-500 font-mono">{error}</p>}

      {result && (
        <div className="space-y-5">
          <div className="space-y-2">
            <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Matched operation</p>
            <MatchedOperation operation={result.matched_operation} />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">
              Findings
              {result.is_valid && (
                <span className="ml-2 text-green-600">· valid</span>
              )}
            </p>
            <FindingsList findings={result.findings} />
          </div>

          {result.corrected_curl && (
            <CorrectedCurl curl={result.corrected_curl} />
          )}
        </div>
      )}
    </div>
    </div>
  );
}
