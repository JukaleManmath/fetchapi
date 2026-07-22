"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface Tab {
  label: string;
  href: string;
  icon?: ReactNode;
  disabled?: boolean;
  badge?: string;
}

export function SourceTabNav({ tabs }: { tabs: Tab[] }) {
  const pathname = usePathname();

  return (
    <nav
      className="flex items-center gap-0 px-7 border-b border-border-1 overflow-x-auto"
      aria-label="Source sections"
    >
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;

        if (tab.disabled) {
          return (
            <span
              key={tab.href}
              className="flex items-center gap-1.5 px-3 py-3 text-xs text-ink-4 cursor-not-allowed opacity-40 whitespace-nowrap"
              aria-disabled="true"
            >
              {tab.icon}
              {tab.label}
            </span>
          );
        }

        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex items-center gap-1.5 px-3 py-3 text-xs border-b-2 transition-all duration-150 whitespace-nowrap",
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
