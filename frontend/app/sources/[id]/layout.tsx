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
    { label: "Operations", href: `/sources/${params.id}`, icon: <List size={13} /> },
    { label: "Schemas", href: `/sources/${params.id}/schemas`, icon: <BookOpen size={13} /> },
    { label: "Auth", href: `/sources/${params.id}/auth`, icon: <KeyRound size={13} /> },
    { label: "Chat", href: `/sources/${params.id}/chat`, icon: <MessageSquare size={13} />, disabled: true, badge: "Phase 4" },
    { label: "Validate", href: `/sources/${params.id}/validate`, icon: <ShieldCheck size={13} />, disabled: true, badge: "Phase 6" },
    { label: "Generate", href: `/sources/${params.id}/generate`, icon: <Code2 size={13} />, disabled: true, badge: "Phase 5" },
  ];

  return (
    <div className="flex flex-col h-full animate-fade-in">
      {/* Source header */}
      <div className="px-6 py-4 border-b border-border">
        <Link href="/" className="text-xs text-text-muted hover:text-text-secondary transition-colors">
          Sources
        </Link>
        <span className="text-xs text-text-muted mx-1.5">/</span>
        <span className="text-xs text-text-primary font-mono">{source.name}</span>
      </div>

      {/* Tab nav */}
      <SourceTabNav tabs={tabs} />

      {/* Page content */}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}
