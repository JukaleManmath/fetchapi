import { ShieldCheck } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";

export const metadata = { title: "Validate" };

export default function ValidatePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-24 gap-4 text-center">
      <EmptyState
        icon={<ShieldCheck size={32} />}
        title="Request validation coming in Phase 6"
        description="Paste a curl command or HTTP request and get deterministic, schema-backed diagnostics."
        action={<Badge variant="warning">Phase 6 - Request Debugger</Badge>}
      />
    </div>
  );
}
