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
        {message.content || (message.loading ? "Thinking…" : "")}
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
            {message.citations.length} source{message.citations.length !== 1 ? "s" : ""}
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
