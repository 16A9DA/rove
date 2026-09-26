from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .schema import AgentNetTask, NormalizedStep


@dataclass
class EvaluationStats:
    num_tasks: int = 0
    num_steps: int = 0
    completed_tasks: int = 0
    unsupported_count: int = 0
    action_counts: Counter = field(default_factory=Counter)

    @property
    def completion_rate(self) -> float | None:
        return self.completed_tasks / self.num_tasks if self.num_tasks else None

    @property
    def avg_steps_per_task(self) -> float | None:
        return self.num_steps / self.num_tasks if self.num_tasks else None

    def to_dict(self) -> dict:
        return {
            "num_tasks": self.num_tasks,
            "num_steps": self.num_steps,
            "completed_tasks": self.completed_tasks,
            "completion_rate": self.completion_rate,
            "avg_steps_per_task": self.avg_steps_per_task,
            "unsupported_count": self.unsupported_count,
            "action_counts": dict(self.action_counts),
        }


def compute_stats(tasks: list[AgentNetTask], normalized: dict[str, list[NormalizedStep]]) -> EvaluationStats:
    stats = EvaluationStats(num_tasks=len(tasks))
    stats.completed_tasks = sum(1 for task in tasks if task.task_completed)

    for steps in normalized.values():
        stats.num_steps += len(steps)
        for step in steps:
            stats.action_counts[step.action.action] += 1
            if step.action.action == "unsupported":
                stats.unsupported_count += 1

    return stats
