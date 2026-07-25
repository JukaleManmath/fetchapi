"use client";
import { useState } from "react";
import { Copy, Check } from "lucide-react";

interface Props { code: string; language: string }

export function CodeBlock({ code, language }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="relative rounded-lg border border-border-2 bg-surface overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border-1">
        <span className="text-2xs font-mono text-ink-4 uppercase tracking-widest">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-2xs font-mono text-ink-4 hover:text-ink transition-colors"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="px-4 py-4 overflow-x-auto text-xs font-mono text-ink-2 leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}
