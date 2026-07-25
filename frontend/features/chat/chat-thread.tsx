"use client";
import { useEffect, useRef } from "react";
import { ChatBubble } from "./chat-bubble";
import type { ChatMessage } from "@/lib/types";

interface Props { messages: ChatMessage[] }

export function ChatThread({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-24 text-center gap-2">
        <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest">Chat</p>
        <p className="text-sm text-ink-3 max-w-xs leading-relaxed">
          Ask anything about this API — operations, parameters, auth, error codes.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 px-6 py-5">
      {messages.map((m) => (
        <ChatBubble key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
