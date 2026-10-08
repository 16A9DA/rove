from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "rove_tasks.db"

# Versioned migrations, applied in order; the applied version lives in schema_version.
# Never stored: API keys, screenshots/preview frames, raw tool arguments or tool output.
MIGRATIONS = [
    """
    CREATE TABLE tasks (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        is_error INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE TABLE steps (
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        step_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        agent TEXT NOT NULL,
        label TEXT NOT NULL,
        status TEXT NOT NULL,
        PRIMARY KEY (task_id, step_id)
    );
    CREATE TABLE paused_runs (
        task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
        messages TEXT NOT NULL,
        saved_at REAL NOT NULL
    );
    CREATE TABLE permission_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        summary TEXT NOT NULL,
        decision TEXT NOT NULL,
        decided_at REAL NOT NULL
    );
    CREATE INDEX idx_tasks_updated ON tasks(updated_at DESC);
    """,
]

_RUN_STATUS = {"ok": "complete", "error": "error", "paused": "paused", "cancelled": "complete"}


class TaskStore:
    # Single-user local app, so no users table. sqlite (stdlib, like MemoryService) behind this
    # class is the only place that knows the storage engine, so Postgres would replace just this file.
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            current = row[0] or 0
            for version, script in enumerate(MIGRATIONS[current:], start=current + 1):
                self._conn.executescript(script)
                self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            self._conn.commit()

    def start_run(self, task_id: str, goal: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tasks (id, goal, status, created_at, updated_at) VALUES (?, ?, 'running', ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = 'running', updated_at = excluded.updated_at",
                (task_id, goal, now, now),
            )
            self._conn.commit()

    def record_event(self, task_id: str, event: dict[str, Any]) -> None:
        kind = event.get("type")
        now = time.time()
        with self._lock:
            if kind == "run_started":
                self._conn.execute("UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?", (now, task_id))
            elif kind == "step":
                self._conn.execute(
                    "INSERT INTO steps (task_id, step_id, seq, agent, label, status) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(task_id, step_id) DO UPDATE SET status = excluded.status",
                    (task_id, event["id"], event["seq"], event.get("agent", ""), event["label"], event["status"]),
                )
            elif kind == "run_finished":
                status = event["status"]
                message = "Stopped." if status == "cancelled" else event.get("message") or None
                self._conn.execute(
                    "UPDATE tasks SET status = ?, result = ?, is_error = ?, updated_at = ? WHERE id = ?",
                    (_RUN_STATUS.get(status, "error"), message, int(status == "error"), now, task_id),
                )
            else:
                return
            self._conn.commit()

    def list_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, goal, status, created_at FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "status": r[2], "created_at": r[3]} for r in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT goal, status, result, is_error, created_at FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            steps = self._conn.execute(
                "SELECT step_id, agent, label, status FROM steps WHERE task_id = ? ORDER BY seq", (task_id,)
            ).fetchall()
        return {
            "id": task_id,
            "goal": row[0],
            "status": row[1],
            "result": row[2],
            "is_error": bool(row[3]),
            "created_at": row[4],
            "steps": [{"id": s[0], "agent": s[1], "label": s[2], "status": s[3]} for s in steps],
        }

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def save_paused(self, task_id: str, messages: list[dict[str, Any]]) -> None:
        with self._lock:
            if self._conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
                return
            self._conn.execute(
                "INSERT INTO paused_runs (task_id, messages, saved_at) VALUES (?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET messages = excluded.messages, saved_at = excluded.saved_at",
                (task_id, json.dumps(messages), time.time()),
            )
            self._conn.commit()

    def pop_paused(self, task_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            row = self._conn.execute("SELECT messages FROM paused_runs WHERE task_id = ?", (task_id,)).fetchone()
            self._conn.execute("DELETE FROM paused_runs WHERE task_id = ?", (task_id,))
            self._conn.commit()
        return json.loads(row[0]) if row else None

    def log_permission(self, task_id: str, tool: str, summary: str, decision: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO permission_log (task_id, tool, summary, decision, decided_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, tool, summary, decision, time.time()),
            )
            self._conn.commit()
