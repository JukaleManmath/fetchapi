import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { ValidationIssue } from "@/lib/types";

const SEVERITY_COLOR: Record<string, string> = {
  error: "text-red-500",
  warning: "text-amber-500",
  info: "text-ink-4",
};

interface Props {
  contractIssues: ValidationIssue[];
  syntaxIssues: ValidationIssue[];
}

export function ValidationReport({ contractIssues, syntaxIssues }: Props) {
  const all = [...contractIssues, ...syntaxIssues];
  if (all.length === 0) {
    return (
      <p className="text-xs text-ink-4 font-mono px-1">No issues detected.</p>
    );
  }

  return (
    <ul className="flex flex-col gap-1.5">
      {contractIssues.map((issue, i) => (
        <li key={`contract-${i}`} className="flex items-start gap-2.5 text-xs">
          <span className={cn("font-mono shrink-0 mt-0.5", SEVERITY_COLOR[issue.severity])}>
            {issue.severity.toUpperCase()}
          </span>
          <span className="text-ink-3 leading-relaxed">{issue.message}</span>
          {issue.field && <Badge variant="muted">{issue.field}</Badge>}
        </li>
      ))}
      {syntaxIssues.map((issue, i) => (
        <li key={`syntax-${i}`} className="flex items-start gap-2.5 text-xs">
          <span className={cn("font-mono shrink-0 mt-0.5", SEVERITY_COLOR[issue.severity])}>
            {issue.severity.toUpperCase()}
          </span>
          <span className="text-ink-3 leading-relaxed">{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}
