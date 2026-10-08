"use client";

import { ActivityFeed } from "@/components/ActivityFeed";
import { AgentStatus } from "@/components/AgentStatus";
import { ComputerPreview } from "@/components/ComputerPreview";
import { MessageInput } from "@/components/MessageInput";
import { MessageList } from "@/components/MessageList";
import type { ActivityStep, AgentState, Message, PreviewFrame } from "@/types/task";

export function Chat({
  messages,
  agentState,
  steps,
  preview,
  onSend,
  onVoiceCommand,
  onResume,
  onStop,
}: {
  messages: Message[];
  agentState: AgentState;
  steps: ActivityStep[];
  preview: PreviewFrame | null;
  onSend: (text: string) => void;
  onVoiceCommand: (text: string) => void;
  onResume?: () => void;
  onStop?: () => void;
}) {
  const inputDisabled = agentState === "thinking" || agentState === "executing";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h1 className="text-sm font-medium text-white/80">Current Task</h1>
        <div className="flex items-center gap-2">
          <AgentStatus state={agentState} />
          {inputDisabled && onStop && (
            <button
              onClick={onStop}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm text-white/70 hover:bg-white/[0.08]"
            >
              Stop
            </button>
          )}
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

      <ComputerPreview frame={preview} steps={steps} />
      <ActivityFeed steps={steps} />

      <MessageInput disabled={inputDisabled} onSend={onSend} onVoiceCommand={onVoiceCommand} />
    </div>
  );
}
