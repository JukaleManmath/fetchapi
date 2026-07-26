"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { BookOpen, List, KeyRound, MessageSquare, ShieldCheck, Code2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getSource } from "@/lib/api";
import type { Source } from "@/lib/types";

import OperationsPage from "./page";
import SchemasPage from "./schemas/page";
import AuthPage from "./auth/page";
import ChatPage from "./chat/page";
import ValidatePage from "./validate/page";
import GeneratePage from "./generate/page";

type TabId = "operations" | "schemas" | "auth" | "chat" | "validate" | "generate";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "operations", label: "Operations", icon: <List size={15} /> },
  { id: "schemas",    label: "Schemas",    icon: <BookOpen size={15} /> },
  { id: "auth",       label: "Auth",       icon: <KeyRound size={15} /> },
  { id: "chat",       label: "Chat",       icon: <MessageSquare size={15} /> },
  { id: "validate",   label: "Validate",   icon: <ShieldCheck size={15} /> },
  { id: "generate",   label: "Generate",   icon: <Code2 size={15} /> },
];

interface Props {
  children: React.ReactNode;
}

export default function SourceLayout({ children: _children }: Props) {
  const params = useParams<{ id: string }>();
  const sourceId = params.id;

  const [source, setSource] = useState<Source | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("operations");

  useEffect(() => {
    if (!sourceId) return;
    getSource(sourceId)
      .then(setSource)
      .catch(() => setSource(null));
  }, [sourceId]);

  const tabParams = { id: sourceId };

  return (
    <div className="flex flex-col h-full animate-fade-in dot-grid">
      {/* Source header */}
      <div className="bg-canvas px-6 py-4 border-b border-border-1">
        <Link href="/" className="text-xs text-ink-3 hover:text-ink transition-colors">
          Sources
        </Link>
        <span className="text-xs text-ink-4 mx-1.5">/</span>
        <span className="text-xs text-ink font-mono">{source?.name ?? sourceId}</span>
      </div>

      {/* Tab nav — onClick-based, no routing */}
      <nav
        className="flex items-center gap-0 px-4 border-b border-border-1 overflow-x-auto shrink-0 bg-canvas"
        aria-label="Source sections"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-3.5 text-sm border-b-2 transition-all duration-150 whitespace-nowrap",
              activeTab === tab.id
                ? "border-ink text-ink font-medium"
                : "border-transparent text-ink-3 hover:text-ink hover:border-border-2"
            )}
            aria-current={activeTab === tab.id ? "page" : undefined}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </nav>

      {/* All tab content panels — mounted once, hidden when inactive */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <div className={activeTab === "operations" ? "h-full" : "hidden"}>
          <OperationsPage params={tabParams} />
        </div>
        <div className={activeTab === "schemas" ? "h-full" : "hidden"}>
          <SchemasPage params={tabParams} />
        </div>
        <div className={activeTab === "auth" ? "h-full" : "hidden"}>
          <AuthPage params={tabParams} />
        </div>
        <div className={activeTab === "chat" ? "h-full" : "hidden"}>
          <ChatPage params={tabParams} />
        </div>
        <div className={activeTab === "validate" ? "h-full" : "hidden"}>
          <ValidatePage params={tabParams} />
        </div>
        <div className={activeTab === "generate" ? "h-full" : "hidden"}>
          <GeneratePage params={tabParams} />
        </div>
      </div>
    </div>
  );
}
