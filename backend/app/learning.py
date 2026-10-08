from __future__ import annotations

from app.memory import MemoryCategory, MemoryService
from app.task_store import TaskStore

# Steps that say nothing reusable about *how* a task was done.
_NOISE = {"Looking at the screen", "Reading the screen layout", "Wrapping up", "Waiting", "Checking open windows"}
MIN_WORKFLOW_STEPS = 3
MAX_WORKFLOW_STEPS = 8


def _clip(text: str, n: int) -> str:
    return " ".join(text.split())[:n]


# Episodes and workflows are written by code from safe activity labels, not by the model, so the
# agent can't be talked into storing arbitrary text and a page can't plant a "workflow".
def learn_from_run(memory: MemoryService, store: TaskStore, task_id: str, success: bool, final_message: str | None) -> None:
    task = store.get_task(task_id)
    if task is None:
        return
    goal = _clip(task["goal"], 100)
    detail = _clip(final_message or "", 150)
    memory.remember(
        MemoryCategory.EPISODIC,
        f'Task "{goal}" {"succeeded" if success else "failed"}' + (f": {detail}" if detail else ""),
        task_id,
    )
    if not success:
        return
    labels: list[str] = []
    for step in task["steps"]:
        if step["status"] != "ok" or step["agent"] == "orchestrator" or step["label"] in _NOISE:
            continue
        if not labels or labels[-1] != step["label"]:
            labels.append(step["label"])
    if len(labels) >= MIN_WORKFLOW_STEPS:
        memory.remember(MemoryCategory.WORKFLOW, f'To do "{_clip(task["goal"], 80)}": ' + " → ".join(labels[:MAX_WORKFLOW_STEPS]), task_id)


def record_feedback(memory: MemoryService, store: TaskStore, task_id: str, rating: str) -> bool:
    task = store.get_task(task_id)
    if task is None:
        return False
    store.set_rating(task_id, rating)
    goal = _clip(task["goal"], 100)
    if rating == "down":
        memory.delete_for_task(task_id, [MemoryCategory.WORKFLOW])
        memory.remember(MemoryCategory.EPISODIC, f'User was unhappy with the result of "{goal}"; do it differently next time', task_id)
    else:
        memory.remember(MemoryCategory.EPISODIC, f'User confirmed the result of "{goal}" was good', task_id)
    return True
