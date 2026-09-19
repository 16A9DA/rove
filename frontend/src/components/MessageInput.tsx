"use client";

import { useState, type KeyboardEvent } from "react";
import { ROVE_API_BASE } from "@/lib/roveApi";

export function MessageInput({
  disabled,
  onSend,
  onVoiceCommand,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
  onVoiceCommand: (text: string) => void;
}) {
  const [value, setValue] = useState("");
  const [listening, setListening] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const toggleMic = async () => {
    setMicError(null);
    try {
      if (!listening) {
        const response = await fetch(`${ROVE_API_BASE}/api/stt/start`, { method: "POST" });
        if (!response.ok) throw new Error((await response.json()).detail ?? "could not start recording");
        setListening(true);
        return;
      }

      setListening(false);
      const response = await fetch(`${ROVE_API_BASE}/api/stt/stop`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json()).detail ?? "could not transcribe");
      const { transcript } = (await response.json()) as { transcript: string };
      if (transcript) onVoiceCommand(transcript);
    } catch (error) {
      setListening(false);
      setMicError(error instanceof Error ? error.message : "microphone error");
    }
  };

  return (
    <div className="border-t border-white/10 bg-white/[0.02] p-4">
      {micError && <p className="mb-2 px-2 text-xs text-red-400">{micError}</p>}
      <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-white/[0.04] p-2 focus-within:border-white/20">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Tell Rove what to do..."
          className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-white/90 placeholder:text-white/30 focus:outline-none disabled:opacity-50"
        />

        <button
          type="button"
          aria-pressed={listening}
          onClick={toggleMic}
          disabled={disabled}
          className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-colors duration-150 active:scale-95 disabled:opacity-50 ${
            listening
              ? "border-blue-400/40 bg-blue-400/20 text-blue-300"
              : "border-white/10 bg-white/[0.04] text-white/60 hover:bg-white/[0.08]"
          }`}
        >
          {listening && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400/40 motion-reduce:animate-none" />
          )}
          <MicIcon className="relative h-4 w-4" />
        </button>

        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-black transition-transform duration-150 active:scale-95 disabled:opacity-30"
        >
          <SendIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function MicIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor" />
      <path
        d="M5 11a7 7 0 0 0 14 0M12 18v4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SendIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M4 12 20 4l-6 16-3-7-7-1Z"
        fill="currentColor"
      />
    </svg>
  );
}
