import { Code2 } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";

export const metadata = { title: "Generate" };

export default function GeneratePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-24 gap-4 text-center">
      <EmptyState
        icon={<Code2 size={32} />}
        title="Code generation coming in Phase 5"
        description="Generate working Python, TypeScript, or Java integration code backed by the spec schema."
        action={<Badge variant="warning">Phase 5 - Integration Generation</Badge>}
      />
    </div>
  );
}
