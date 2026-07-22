"use client";

import { useScrollReveal } from "@/lib/hooks/use-scroll-reveal";
import type { HTMLAttributes } from "react";

export function ScrollRevealContainer({
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  const ref = useScrollReveal();

  return (
    <div ref={ref as React.RefObject<HTMLDivElement>} {...props}>
      {children}
    </div>
  );
}
