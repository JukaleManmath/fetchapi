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

  /* Empty state — input centered in the page */
  if (messages.length === 0) {
    return (
      <div className="relative flex flex-col items-center justify-center h-full px-6">
        {/* Gradient overlay so dot-grid doesn't compete with text */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_50%,rgba(255,255,255,0.6)_0%,transparent_100%)]" />
        <div className="relative z-10 w-full max-w-2xl space-y-8">
          <div className="text-center space-y-2">
            <p className="text-xs font-mono text-ink-4 uppercase tracking-widest">Chat</p>
            <h2 className="text-2xl font-semibold text-ink">Ask about this API</h2>
            <p className="text-sm text-ink-3 leading-relaxed">
              Ask anything — operations, parameters, authentication, error codes.
            </p>
          </div>
          <div className="rounded-xl border border-border-1 bg-canvas shadow-card overflow-hidden">
            <ChatInput onSend={handleSend} disabled={streaming} />
          </div>
        </div>
      </div>
    );
  }

  /* Active chat — thread scrolls, input pinned at bottom */
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 min-h-0 overflow-y-auto">
        <ChatThread messages={messages} />
      </div>
      <ChatInput onSend={handleSend} disabled={streaming} />
    </div>
  );
}
