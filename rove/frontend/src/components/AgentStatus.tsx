import type { AgentState } from "@/types/task";

const STATUS_COPY: Record<AgentState, string> = {
  idle: "Idle",
  listening: "Listening",
  thinking: "Thinking",
  executing: "Executing",
  complete: "Done",
  error: "Error",
};

const STATUS_DOT: Record<AgentState, string> = {
  idle: "bg-white/30",
  listening: "bg-blue-400",
  thinking: "bg-amber-400",
  executing: "bg-emerald-400",
  complete: "bg-emerald-400",
  error: "bg-red-400",
};

export function AgentStatus({ state }: { state: AgentState }) {
  const pulsing = state === "listening" || state === "thinking" || state === "executing";

  return (
    <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm text-white/70">
      <span className="relative flex h-2 w-2">
        {pulsing && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full ${STATUS_DOT[state]} opacity-60 motion-reduce:animate-none`}
          />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${STATUS_DOT[state]}`} />
      </span>
      {STATUS_COPY[state]}
    </div>
  );
}
