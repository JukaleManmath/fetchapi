"use client";

import { useState, useCallback } from "react";
import { ChatThread } from "@/features/chat/chat-thread";
import { ChatInput } from "@/features/chat/chat-input";
import { streamQuery } from "@/lib/api";
import type { ChatMessage, Citation } from "@/lib/types";

interface Props { params: { id: string } }

export default function ChatPage({ params }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);

  const handleSend = useCallback((query: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
    };
    const assistantId = crypto.randomUUID();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      loading: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);

    streamQuery(
      params.id,
      query,
      (token) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + token } : m
          )
        );
      },
      (evidenceCitations) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, evidence_citations: evidenceCitations }
              : m
          )
        );
      },
      (citations: Citation[], supportStatus: string) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, citations, support_status: supportStatus }
              : m
          )
        );
      },
      () => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, loading: false } : m
          )
        );
        setStreaming(false);
      },
      (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${err.message}`, loading: false }
              : m
          )
        );
        setStreaming(false);
      }
    );
  }, [params.id]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto">
        <ChatThread messages={messages} />
      </div>
      <ChatInput onSend={handleSend} disabled={streaming} />
    </div>
  );
}
