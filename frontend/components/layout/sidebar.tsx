"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const NAV: NavItem[] = [
  { label: "Sources", href: "/",       icon: <Database size={16} /> },
  { label: "Ingest",  href: "/ingest", icon: <Upload   size={16} /> },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-52 shrink-0 flex flex-col bg-surface-1 border-r border-border-1 h-full">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-border-1">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-6 h-6 rounded bg-ink flex items-center justify-center">
            <span className="font-mono text-canvas text-[10px] font-bold">F</span>
          </div>
          <span className="font-mono text-sm font-semibold text-ink tracking-tight">
            FetchAPI
          </span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="flex flex-col gap-0.5" role="list">
          {NAV.map((item) => {
            const isActive =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2.5 rounded text-sm transition-all duration-150",
                    isActive
                      ? "bg-ink text-canvas font-medium"
                      : "text-ink-2 hover:text-ink hover:bg-surface-2"
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  {item.icon}
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border-1">
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
          className="text-2xs font-mono text-ink-4 hover:text-ink-2 transition-colors underline underline-offset-2"
        >
          API Docs
        </a>
      </div>
    </aside>
  );
}
