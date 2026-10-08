import type { ActivityStep } from "@/types/task";

const ICON: Record<ActivityStep["status"], { glyph: string; style: string }> = {
  running: { glyph: "●", style: "text-amber-400 animate-pulse motion-reduce:animate-none" },
  ok: { glyph: "✓", style: "text-emerald-400" },
  error: { glyph: "✕", style: "text-red-400" },
};

export function ActivityFeed({ steps }: { steps: ActivityStep[] }) {
  if (steps.length === 0) return null;

  return (
    <ul
      aria-label="Agent activity"
      className="mx-6 mb-3 max-h-40 space-y-1 overflow-y-auto rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm"
    >
      {steps.map((step) => (
        <li key={step.id} className="flex items-baseline gap-2 text-white/70">
          <span className={`w-3 shrink-0 text-xs ${ICON[step.status].style}`}>{ICON[step.status].glyph}</span>
          <span className="truncate">{step.label}</span>
        </li>
      ))}
    </ul>
  );
}
