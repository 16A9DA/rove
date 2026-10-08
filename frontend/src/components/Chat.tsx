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
  loading,
  approval,
  rating,
  onFeedback,
  onSend,
  onVoiceCommand,
  onResume,
  onStop,
}: {
  messages: Message[];
  agentState: AgentState;
  steps: ActivityStep[];
  preview: PreviewFrame | null;
  loading: boolean;
  approval: string | null;
  rating: "up" | "down" | null;
  onFeedback?: (rating: "up" | "down") => void;
  onSend: (text: string) => void;
  onVoiceCommand: (text: string) => void;
  onResume?: (decision?: "approve" | "deny") => void;
  onStop?: () => void;
}) {
  const inputDisabled = agentState === "thinking" || agentState === "executing";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
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
          {agentState === "paused" && onResume && approval && (
            <>
              <span className="max-w-64 truncate text-sm text-amber-300/80">Approve: {approval}</span>
              <button
                onClick={() => onResume("deny")}
                className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm text-white/70 hover:bg-white/[0.08]"
              >
                Cancel
              </button>
              <button
                onClick={() => onResume("approve")}
                className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-sm text-emerald-200 hover:bg-emerald-400/20"
              >
                Approve
              </button>
            </>
          )}
          {agentState === "paused" && onResume && !approval && (
            <button
              onClick={() => onResume()}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm text-white/70 hover:bg-white/[0.08]"
            >
              Continue
            </button>
          )}
        </div>
      </div>

      <MessageList messages={messages} agentState={agentState} loading={loading} onExampleClick={onSend} />

      {(agentState === "complete" || agentState === "error") && messages.length > 0 && onFeedback && (
        <div className="mx-6 mb-2 flex items-center gap-2 text-xs text-white/40">
          {rating ? (
            <span>Thanks, noted.</span>
          ) : (
            <>
              <span>Was this right?</span>
              <button onClick={() => onFeedback("up")} className="rounded-full border border-white/10 px-2.5 py-1 hover:bg-white/[0.06]">
                Yes
              </button>
              <button onClick={() => onFeedback("down")} className="rounded-full border border-white/10 px-2.5 py-1 hover:bg-white/[0.06]">
                No
              </button>
            </>
          )}
        </div>
      )}

      <ComputerPreview frame={preview} steps={steps} />
      <ActivityFeed steps={steps} />

      <MessageInput disabled={inputDisabled} onSend={onSend} onVoiceCommand={onVoiceCommand} />
    </div>
  );
}
