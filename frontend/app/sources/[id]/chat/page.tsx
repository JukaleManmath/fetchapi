import { MessageSquare } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";

export const metadata = { title: "Chat" };

export default function ChatPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-24 gap-4 text-center">
      <EmptyState
        icon={<MessageSquare size={32} />}
        title="Chat coming in Phase 4"
        description="Grounded Q&A with streamed answers and citation cards. Requires the hybrid retrieval pipeline from Phase 3."
        action={<Badge variant="warning">Phase 4 - Grounded Q&A</Badge>}
      />
    </div>
  );
}
