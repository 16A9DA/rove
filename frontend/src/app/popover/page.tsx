"use client";

import { useEffect, useState } from "react";
import { streamEvents } from "@/lib/roveApi";

type QuickState = "idle" | "listening" | "transcribing" | "executing" | "complete" | "error";

const TITLE: Record<QuickState, string> = {
  idle: "Rove",
  listening: "Listening...",
  transcribing: "Transcribing...",
  executing: "Working...",
  complete: "Done",
  error: "Needs attention",
};

const DOT: Record<QuickState, string> = {
  idle: "bg-white/30",
  listening: "bg-blue-400",
  transcribing: "bg-amber-400",
  executing: "bg-emerald-400",
  complete: "bg-emerald-400",
  error: "bg-red-400",
};

export default function PopoverPage() {
  const [state, setState] = useState<QuickState>("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    document.documentElement.style.background = "transparent";
    document.body.style.background = "transparent";
    const controller = new AbortController();
    (async () => {
      while (!controller.signal.aborted) {
        try {
          await streamEvents(
            "/api/quick/events",
            (next: { state: QuickState; message: string }) => {
              setState(next.state);
              setMessage(next.message);
            },
            controller.signal,
          );
        } catch {
          // backend not up yet; retry below
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    })();
    return () => controller.abort();
  }, []);

  const pulsing = state === "listening" || state === "transcribing" || state === "executing";

  return (
    <div className="flex h-full items-center justify-center p-3">
      <div role="status" aria-live="polite" className="animate-message-in flex w-full flex-col gap-2 rounded-2xl border border-white/10 bg-[#111113]/95 px-5 py-4 shadow-2xl backdrop-blur">
        <div className="flex items-center gap-2.5 text-sm font-medium text-white">
          <span className="relative flex h-2.5 w-2.5">
            {pulsing && (
              <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${DOT[state]} opacity-60 motion-reduce:animate-none`} />
            )}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${DOT[state]}`} />
          </span>
          {TITLE[state]}
        </div>
        {message && state !== "listening" && <p className="line-clamp-3 text-sm text-white/60">{message}</p>}
      </div>
    </div>
  );
}
