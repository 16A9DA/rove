from __future__ import annotations

from .parser import parse_code
from .schema import AgentNetTask, NormalizedStep


def normalize_task(task: AgentNetTask) -> list[NormalizedStep]:
    return [
        NormalizedStep(task_id=task.task_id, step_index=step.index, action=parse_code(step.code, step.action))
        for step in task.steps
    ]


def normalize_tasks(tasks: list[AgentNetTask]) -> dict[str, list[NormalizedStep]]:
    return {task.task_id: normalize_task(task) for task in tasks}
