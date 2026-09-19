from __future__ import annotations

import sqlite3
from enum import Enum
from pathlib import Path

# ponytail: one table, category as a plain column — five separate tables would be
# unrequested structure for what's really one shape (category, content, timestamp).
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "rove_memory.db"


class MemoryCategory(str, Enum):
    # Matches the diagram's five memory kinds. TASK is per-run working memory (what
    # the current goal needs), the other four are meant to accumulate across runs.
    PERSONAL = "personal"
    EPISODIC = "episodic"
    WORKFLOW = "workflow"
    TASK = "task"
    STRUCTURED = "structured"


class MemoryService:
    """Shared memory store the orchestrator retrieves from before delegating and
    writes back to after learning something; sub-agents get the same recalled
    context read-only via their system prompt rather than querying separately —
    one writer keeps it simple, no sync between multiple write paths."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "category TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        self._conn.commit()

    def remember(self, category: MemoryCategory, content: str) -> None:
        self._conn.execute("INSERT INTO memories (category, content) VALUES (?, ?)", (MemoryCategory(category).value, content))
        self._conn.commit()

    def recall(self, limit: int = 20) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT category, content FROM memories ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return list(reversed(rows))  # oldest-first, reads like a timeline

    def format_context(self, limit: int = 20) -> str:
        rows = self.recall(limit)
        if not rows:
            return ""
        lines = "\n".join(f"- [{category}] {content}" for category, content in rows)
        return f"What you remember from previous tasks:\n{lines}"
