import { TaskHistory } from "@/components/TaskHistory";
import type { Task } from "@/types/task";

export function Sidebar({
  tasks,
  activeTaskId,
  onSelectTask,
  onNewTask,
  onOpenSettings,
}: {
  tasks: Task[];
  activeTaskId: string | null;
  onSelectTask: (id: string) => void;
  onNewTask: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-white/10 bg-white/[0.02]">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white text-sm font-semibold text-black">
          R
        </div>
        <span className="text-sm font-medium text-white/90">Rove</span>
      </div>

      <div className="px-3">
        <button
          onClick={onNewTask}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/[0.08] active:scale-[0.98]"
        >
          + New Task
        </button>
      </div>

      <nav className="mt-4 flex-1 overflow-y-auto px-3">
        <p className="px-3 pb-1 text-xs font-medium tracking-wide text-white/30">TASK HISTORY</p>
        <TaskHistory tasks={tasks} activeTaskId={activeTaskId} onSelect={onSelectTask} />
      </nav>

      <div className="border-t border-white/10 p-3">
        <button
          onClick={onOpenSettings}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-white/60 transition-colors duration-150 hover:bg-white/[0.04] hover:text-white/90"
        >
          Settings
        </button>
      </div>
    </aside>
  );
}
