import { cn, httpMethodColor } from "@/lib/utils";

interface Props {
  operation: { method: string; path: string } | null;
}

export function MatchedOperation({ operation }: Props) {
  if (!operation) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="font-mono text-red-500">NO MATCH</span>
        <span className="text-ink-4">No matching operation found in the spec</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-md border border-border-1 bg-canvas text-xs">
      <span className={cn("font-mono font-bold uppercase shrink-0", httpMethodColor(operation.method))}>
        {operation.method}
      </span>
      <span className="font-mono text-ink-2">{operation.path}</span>
    </div>
  );
}
