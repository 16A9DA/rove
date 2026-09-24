import type { Task } from "@/types/task";

const STATUS_STYLE: Record<Task["status"], string> = {
  running: "bg-amber-400",
  complete: "bg-emerald-400",
  error: "bg-red-400",
  paused: "bg-amber-400",
};

export function TaskHistory({
  tasks,
  activeTaskId,
  onSelect,
}: {
  tasks: Task[];
  activeTaskId: string | null;
  onSelect: (id: string) => void;
}) {
  if (tasks.length === 0) {
    return <p className="px-3 py-2 text-xs text-white/30">No tasks yet.</p>;
  }

  return (
    <ul className="space-y-0.5">
      {tasks.map((task) => (
        <li key={task.id}>
          <button
            onClick={() => onSelect(task.id)}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 ${
              task.id === activeTaskId
                ? "bg-white/[0.08] text-white/90"
                : "text-white/50 hover:bg-white/[0.04] hover:text-white/80"
            }`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_STYLE[task.status]}`} />
            <span className="truncate">{task.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
