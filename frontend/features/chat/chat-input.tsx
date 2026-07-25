"use client";
import { useRef } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onSend: (query: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    const value = ref.current?.value.trim();
    if (!value || disabled) return;
    onSend(value);
    if (ref.current) ref.current.value = "";
  }

  return (
    <div className="flex gap-2 items-end border-t border-border-1 px-5 py-4">
      <textarea
        ref={ref}
        rows={2}
        placeholder="Ask anything about this API… (Enter to send, Shift+Enter for newline)"
        disabled={disabled}
        onKeyDown={handleKeyDown}
        className="flex-1 resize-none bg-transparent text-sm text-ink placeholder:text-ink-4 outline-none leading-relaxed disabled:opacity-50"
      />
      <Button size="sm" onClick={submit} disabled={disabled}>
        <Send size={13} />
        Send
      </Button>
    </div>
  );
}
