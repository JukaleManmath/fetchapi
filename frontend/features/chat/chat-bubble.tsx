import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { CitationCard } from "./citation-card";
import { RetrievalInspector } from "./retrieval-inspector";
import type { ChatMessage } from "@/lib/types";

const STATUS_VARIANT: Record<string, "default" | "warning" | "muted" | "inverted"> = {
  SUPPORTED: "inverted",
  PARTIALLY_SUPPORTED: "warning",
  INSUFFICIENT_EVIDENCE: "muted",
  CONFLICTING_EVIDENCE: "warning",
  VALIDATION_FAILED: "warning",
};

interface Props { message: ChatMessage }

export function ChatBubble({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] px-4 py-2.5 rounded-xl bg-ink text-canvas text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 max-w-[85%]">
      <div className={cn(
        "px-4 py-3 rounded-xl border border-border-1 bg-canvas text-sm leading-relaxed text-ink-2",
        message.loading && "animate-pulse"
      )}>
        {message.loading && !message.content ? (
          "Thinking…"
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const isBlock = className?.startsWith("language-");
                return isBlock ? (
                  <pre className="my-2 p-3 rounded-md bg-surface-2 overflow-x-auto text-xs font-mono text-ink-2">
                    <code className={className} {...props}>{children}</code>
                  </pre>
                ) : (
                  <code className="px-1 py-0.5 rounded bg-surface-2 font-mono text-xs text-ink-2" {...props}>{children}</code>
                );
              },
              p({ children }) { return <p className="mb-2 last:mb-0">{children}</p>; },
              ul({ children }) { return <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>; },
              ol({ children }) { return <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>; },
              li({ children }) { return <li className="leading-relaxed">{children}</li>; },
              strong({ children }) { return <strong className="font-semibold text-ink">{children}</strong>; },
              a({ href, children }) { return <a href={href} className="text-ink-2 underline" target="_blank" rel="noopener noreferrer">{children}</a>; },
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>

      {message.support_status && (
        <div className="flex items-center gap-2 px-1">
          <Badge variant={STATUS_VARIANT[message.support_status] ?? "muted"}>
            {message.support_status.replace(/_/g, " ").toLowerCase()}
          </Badge>
        </div>
      )}

      {message.citations && message.citations.length > 0 && (
        <div className="flex flex-col gap-1.5 pl-1">
          <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">
            {message.citations.length} cited source{message.citations.length !== 1 ? "s" : ""}
          </p>
          {message.citations.map((c, i) => (
            <CitationCard key={c.chunk_id} citation={c} index={i} />
          ))}
        </div>
      )}

      {message.evidence_citations && message.evidence_citations.length > 0 && (
        <RetrievalInspector citations={message.evidence_citations} />
      )}
    </div>
  );
}
