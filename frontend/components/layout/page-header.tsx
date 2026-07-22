import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function PageHeader({ title, description, action, className }: PageHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-7 py-6 border-b border-border-1", className)}>
      <div>
        <h1 className="text-lg font-display font-bold text-ink">{title}</h1>
        {description && (
          <p className="mt-1 text-xs text-ink-3 leading-relaxed">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0 mt-0.5">{action}</div>}
    </div>
  );
}
