from __future__ import annotations

from dataclasses import dataclass

from .loader import load_tasks
from .normalize import normalize_tasks
from .schema import AgentNetTask, NormalizedStep
from .stats import EvaluationStats, compute_stats


@dataclass
class EvaluationReport:
    tasks: list[AgentNetTask]
    normalized: dict[str, list[NormalizedStep]]
    stats: EvaluationStats


def run_evaluation(limit: int = 5, source: str = "ubuntu") -> EvaluationReport:
    # loads/normalizes/reports only — never runs against a ComputerController (see README)
    tasks = load_tasks(limit=limit, source=source)
    normalized = normalize_tasks(tasks)
    return EvaluationReport(tasks=tasks, normalized=normalized, stats=compute_stats(tasks, normalized))
