"use client";

import { AgentStatus } from "@/components/AgentStatus";
import { MessageInput } from "@/components/MessageInput";
import { MessageList } from "@/components/MessageList";
import type { AgentState, Message } from "@/types/task";

export function Chat({
  messages,
  agentState,
  onSend,
  onVoiceCommand,
  onResume,
}: {
  messages: Message[];
  agentState: AgentState;
  onSend: (text: string) => void;
  onVoiceCommand: (text: string) => void;
  onResume?: () => void;
}) {
  const inputDisabled = agentState === "thinking" || agentState === "executing";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h1 className="text-sm font-medium text-white/80">Current Task</h1>
        <div className="flex items-center gap-2">
          <AgentStatus state={agentState} />
          {agentState === "paused" && onResume && (
            <button
              onClick={onResume}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm text-white/70 hover:bg-white/[0.08]"
            >
              Continue
            </button>
          )}
        </div>
      </div>

      <MessageList messages={messages} agentState={agentState} onExampleClick={onSend} />

      <MessageInput disabled={inputDisabled} onSend={onSend} onVoiceCommand={onVoiceCommand} />
    </div>
  );
}
