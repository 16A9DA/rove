"use client";

import { AgentStatus } from "@/components/AgentStatus";
import { MessageInput } from "@/components/MessageInput";
import { MessageList } from "@/components/MessageList";
import type { AgentState, Message } from "@/types/task";

export function Chat({
  messages,
  agentState,
  onSend,
}: {
  messages: Message[];
  agentState: AgentState;
  onSend: (text: string) => void;
}) {
  const inputDisabled = agentState === "thinking" || agentState === "executing";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h1 className="text-sm font-medium text-white/80">Current Task</h1>
        <AgentStatus state={agentState} />
      </div>

      <MessageList messages={messages} agentState={agentState} onExampleClick={onSend} />

      <MessageInput disabled={inputDisabled} onSend={onSend} />
    </div>
  );
}
