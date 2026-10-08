"use client";

import { useState } from "react";
import type { ActivityStep, PreviewFrame } from "@/types/task";

export function ComputerPreview({ frame, steps }: { frame: PreviewFrame | null; steps: ActivityStep[] }) {
  const [hidden, setHidden] = useState(false);
  if (!frame) return null;

  const current = [...steps].reverse().find((s) => s.status === "running");
  const where = frame.url ?? frame.app ?? "Screen";

  return (
    <section aria-label="Live preview" className="mx-6 mb-3 overflow-hidden rounded-xl border border-white/10 bg-white/[0.03]">
      <div className="flex items-center justify-between gap-3 px-4 py-2 text-xs text-white/50">
        <span className="truncate">{where}</span>
        <div className="flex shrink-0 items-center gap-3">
          {current && <span className="truncate text-white/70">{current.label}</span>}
          <button onClick={() => setHidden((h) => !h)} className="hover:text-white/80">
            {hidden ? "Show" : "Hide"}
          </button>
        </div>
      </div>
      {!hidden && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={frame.src} alt={`Live view of ${where}`} className="max-h-64 w-full bg-black/40 object-contain" />
      )}
    </section>
  );
}
