"use client";
import { useRef } from "react";
import { Button } from "@/components/ui/button";

interface Props {
  onValidate: (curl: string) => void;
  loading: boolean;
}

export function CurlInput({ onValidate, loading }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function handleSubmit() {
    const value = ref.current?.value.trim();
    if (!value || loading) return;
    onValidate(value);
  }

  return (
    <div className="space-y-3">
      <textarea
        ref={ref}
        rows={5}
        placeholder={`curl -X POST https://api.example.com/pets \\\n  -H "Content-Type: application/json" \\\n  -d '{"name": "Rex"}'`}
        className="w-full resize-none bg-surface border border-border-2 rounded-lg px-4 py-3 text-xs font-mono text-ink placeholder:text-ink-4 outline-none focus:border-border-3 leading-relaxed"
      />
      <Button size="sm" onClick={handleSubmit} disabled={loading}>
        {loading ? "Validating…" : "Validate"}
      </Button>
    </div>
  );
}
