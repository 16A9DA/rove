from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentNetStep:
    index: int
    image: str | None
    code: str | None
    action: str | None
    observation: str | None
    thought: str | None
    reflection: str | None
    last_step_correct: bool | None
    last_step_redundant: bool | None

    @classmethod
    def from_raw(cls, index: int, raw: dict[str, Any]) -> AgentNetStep:
        value = raw.get("value") or {}
        return cls(
            index=raw.get("index", index),
            image=raw.get("image"),
            code=value.get("code"),
            action=value.get("action"),
            observation=value.get("observation"),
            thought=value.get("thought"),
            reflection=value.get("reflection"),
            last_step_correct=value.get("last_step_correct"),
            last_step_redundant=value.get("last_step_redundant"),
        )


@dataclass
class AgentNetTask:
    task_id: str
    instruction: str
    task_completed: bool | None
    domain: str | None
    steps: list[AgentNetStep] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> AgentNetTask:
        traj = raw.get("traj") or []
        return cls(
            task_id=raw["task_id"],
            instruction=raw.get("instruction", ""),
            task_completed=raw.get("task_completed"),
            domain=raw.get("domain"),
            steps=[AgentNetStep.from_raw(i, step) for i, step in enumerate(traj)],
        )


@dataclass
class RoveAction:
    action: str  # click | type | keypress | hotkey | scroll | drag | move | wait | finish | unsupported
    target: dict[str, Any] | None = None  # {"description": ...} — proxy label, not a verified UI element
    text: str | None = None
    keys: list[str] | None = None
    amount: float | None = None
    click_type: str | None = None  # single | double | triple | right
    success: bool | None = None
    coordinate: dict[str, Any] | None = None  # dataset-specific fallback, never primary
    raw_code: str | None = None
    reason: str | None = None  # populated for "unsupported"


@dataclass
class NormalizedStep:
    task_id: str
    step_index: int
    action: RoveAction
