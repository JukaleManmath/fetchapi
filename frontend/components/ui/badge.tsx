import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Variant = "default" | "inverted" | "success" | "warning" | "error" | "muted";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variantClasses: Record<Variant, string> = {
  default:  "bg-surface-2 text-ink-2 border border-border-1",
  inverted: "bg-ink text-canvas border border-ink",
  success:  "bg-surface-1 text-emerald-700 border border-emerald-200",
  warning:  "bg-surface-1 text-amber-700 border border-amber-200",
  error:    "bg-surface-1 text-red-700 border border-red-200",
  muted:    "bg-surface-1 text-ink-4 border border-border-1",
};

export function Badge({
  variant = "default",
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 text-2xs font-mono font-medium rounded-sm tracking-wide uppercase",
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
