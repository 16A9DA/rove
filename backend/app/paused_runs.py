from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.task_store import TaskStore

# In-memory first (the common case); a configured TaskStore makes paused runs survive a restart.
_paused: dict[str, list[dict[str, Any]]] = {}
_store: TaskStore | None = None


def configure(store: TaskStore | None) -> None:
    global _store
    _store = store


# Screenshots are large and show whatever was on screen; a stub is enough to resume the conversation.
def _without_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**m, "content": "[earlier screenshot omitted]"} if m.get("role") == "user" and isinstance(m.get("content"), list) else m
        for m in messages
    ]


def save(task_id: str, messages: list[dict[str, Any]]) -> None:
    _paused[task_id] = messages
    if _store is not None:
        _store.save_paused(task_id, _without_images(messages))


def pop(task_id: str) -> list[dict[str, Any]] | None:
    in_memory = _paused.pop(task_id, None)
    stored = _store.pop_paused(task_id) if _store is not None else None
    return in_memory if in_memory is not None else stored
