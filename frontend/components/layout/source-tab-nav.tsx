"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface Tab {
  label: string;
  href: string;
  icon?: ReactNode;
}

export function SourceTabNav({ tabs }: { tabs: Tab[] }) {
  const pathname = usePathname();

  return (
    <nav
      className="flex items-center gap-0 px-4 border-b border-border-1 overflow-x-auto shrink-0 bg-canvas"
      aria-label="Source sections"
    >
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;

        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex items-center gap-2 px-4 py-3.5 text-sm border-b-2 transition-all duration-150 whitespace-nowrap",
              isActive
                ? "border-ink text-ink font-medium"
                : "border-transparent text-ink-3 hover:text-ink hover:border-border-2"
            )}
            aria-current={isActive ? "page" : undefined}
          >
            {tab.icon}
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
