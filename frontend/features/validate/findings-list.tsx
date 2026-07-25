import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { DiagnosticFinding } from "@/lib/types";

const SEVERITY_COLOR: Record<string, string> = {
  error: "text-red-500",
  warning: "text-amber-500",
  info: "text-ink-4",
};

interface Props { findings: DiagnosticFinding[] }

export function FindingsList({ findings }: Props) {
  if (findings.length === 0) {
    return <p className="text-xs text-green-600 font-mono">No issues found — request looks valid.</p>;
  }

  return (
    <ul className="flex flex-col gap-2">
      {findings.map((f, i) => (
        <li key={i} className="flex items-start gap-2.5 text-xs">
          <span className={cn("font-mono shrink-0 mt-0.5 w-14", SEVERITY_COLOR[f.severity])}>
            {f.severity.toUpperCase()}
          </span>
          <div className="flex-1 min-w-0">
            <span className="text-ink-3 leading-relaxed">{f.message}</span>
            {f.field && <Badge variant="muted" className="ml-1.5">{f.field}</Badge>}
          </div>
          <Badge variant="muted">{f.category.replace(/_/g, " ").toLowerCase()}</Badge>
        </li>
      ))}
    </ul>
  );
}
