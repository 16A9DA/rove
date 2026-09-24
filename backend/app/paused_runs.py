from __future__ import annotations

from typing import Any

# ponytail: single-process in-memory store, lost on restart — matches the
# lru_cache singleton pattern already used for controllers/memory in main.py.
_paused: dict[str, list[dict[str, Any]]] = {}


def save(task_id: str, messages: list[dict[str, Any]]) -> None:
    _paused[task_id] = messages


def pop(task_id: str) -> list[dict[str, Any]] | None:
    return _paused.pop(task_id, None)
