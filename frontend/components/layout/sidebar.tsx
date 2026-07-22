"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, Upload, MessageSquare, ShieldCheck, Code2, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  phase?: string;
}

const NAV: NavItem[] = [
  { label: "Sources",  href: "/",         icon: <Database   size={14} /> },
  { label: "Ingest",   href: "/ingest",   icon: <Upload     size={14} /> },
  { label: "Chat",     href: "/chat",     icon: <MessageSquare size={14} />, phase: "4" },
  { label: "Generate", href: "/generate", icon: <Code2      size={14} />, phase: "5" },
  { label: "Validate", href: "/validate", icon: <ShieldCheck size={14} />, phase: "6" },
  { label: "Eval",     href: "/eval",     icon: <BarChart3  size={14} />, phase: "9" },
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
        <p className="px-3 mb-2 text-2xs font-mono text-ink-4 uppercase tracking-widest">
          Navigation
        </p>
        <ul className="flex flex-col gap-0.5" role="list">
          {NAV.map((item) => {
            const isActive =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const isLocked = !!item.phase;

            return (
              <li key={item.href}>
                {isLocked ? (
                  <span
                    className="flex items-center gap-2.5 px-3 py-2 rounded text-xs text-ink-4 cursor-not-allowed select-none"
                    aria-disabled="true"
                    title={`Available in Phase ${item.phase}`}
                  >
                    <span className="opacity-50">{item.icon}</span>
                    <span className="opacity-50 flex-1">{item.label}</span>
                    <span className="text-2xs font-mono bg-surface-2 border border-border-1 px-1.5 py-0.5 rounded text-ink-4">
                      P{item.phase}
                    </span>
                  </span>
                ) : (
                  <Link
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-2 rounded text-xs transition-all duration-150",
                      isActive
                        ? "bg-ink text-canvas font-medium"
                        : "text-ink-2 hover:text-ink hover:bg-surface-2"
                    )}
                    aria-current={isActive ? "page" : undefined}
                  >
                    {item.icon}
                    {item.label}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border-1 space-y-1">
        <p className="text-2xs font-mono text-ink-4">Phase 2 - Chunking</p>
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
