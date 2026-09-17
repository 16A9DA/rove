"use client";

import { useEffect, useRef } from "react";
import type { AgentState, Message } from "@/types/task";

const EXAMPLE_PROMPTS = [
  "Check my purchase history and tell me if I have any subscriptions.",
  "Find the PDF I downloaded today and move it to Documents.",
  "Open Finder and open my Downloads folder.",
];

export function MessageList({
  messages,
  agentState,
  onExampleClick,
}: {
  messages: Message[];
  agentState: AgentState;
  onExampleClick: (prompt: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, agentState]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04]">
          <span className="text-xl">✦</span>
        </div>
        <div className="space-y-1">
          <p className="text-lg font-medium text-white/90">What do you want Rove to do?</p>
          <p className="text-sm text-white/50">Give a goal. Rove plans it and operates your computer.</p>
        </div>
        <div className="flex flex-col gap-2">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => onExampleClick(prompt)}
              className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-left text-sm text-white/70 transition-colors duration-150 hover:bg-white/[0.07] active:scale-[0.98]"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.role === "user" ? "justify-end" : "justify-start"} animate-message-in`}
        >
          <div
            className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              message.role === "user"
                ? "bg-white text-black"
                : message.isError
                  ? "border border-red-400/30 bg-red-400/10 text-red-200"
                  : "border border-white/10 bg-white/[0.05] text-white/90"
            }`}
          >
            {message.content}
          </div>
        </div>
      ))}

      {agentState === "thinking" && (
        <div className="flex justify-start">
          <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-white/[0.05] px-4 py-3">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 animate-thinking-dot rounded-full bg-white/50"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
