"use client";

import { useTilt } from "@/lib/hooks/use-tilt";
import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

interface TiltCardProps extends HTMLAttributes<HTMLDivElement> {
  intensity?: number;
}

export function TiltCard({ className, children, ...props }: TiltCardProps) {
  const { ref, onMouseMove, onMouseLeave } = useTilt();

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className={cn("tilt-card rounded-lg bg-canvas border border-border-1 shadow-card-sm", className)}
      {...props}
    >
      {children}
    </div>
  );
}
