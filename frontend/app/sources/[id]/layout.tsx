import Link from "next/link";
import { notFound } from "next/navigation";
import { BookOpen, List, KeyRound, MessageSquare, ShieldCheck, Code2 } from "lucide-react";
import { getSource } from "@/lib/api";
import { SourceTabNav } from "@/components/layout/source-tab-nav";

interface Props {
  children: React.ReactNode;
  params: { id: string };
}

export default async function SourceLayout({ children, params }: Props) {
  let source;
  try {
    source = await getSource(params.id);
  } catch {
    notFound();
  }

  const tabs = [
    { label: "Operations", href: `/sources/${params.id}`, icon: <List size={15} /> },
    { label: "Schemas", href: `/sources/${params.id}/schemas`, icon: <BookOpen size={15} /> },
    { label: "Auth", href: `/sources/${params.id}/auth`, icon: <KeyRound size={15} /> },
    { label: "Chat", href: `/sources/${params.id}/chat`, icon: <MessageSquare size={15} /> },
    { label: "Validate", href: `/sources/${params.id}/validate`, icon: <ShieldCheck size={15} /> },
    { label: "Generate", href: `/sources/${params.id}/generate`, icon: <Code2 size={15} /> },
  ];

  return (
    <div className="flex flex-col h-full animate-fade-in dot-grid">
      {/* Source header — solid so dot-grid doesn't bleed through chrome */}
      <div className="bg-canvas px-6 py-4 border-b border-border-1">
        <Link href="/" className="text-xs text-ink-3 hover:text-ink transition-colors">
          Sources
        </Link>
        <span className="text-xs text-ink-4 mx-1.5">/</span>
        <span className="text-xs text-ink font-mono">{source.name}</span>
      </div>

      {/* Tab nav */}
      <SourceTabNav tabs={tabs} />

      {/* Page content — dot-grid shows through as ambient background */}
      <div className="flex-1 min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}
