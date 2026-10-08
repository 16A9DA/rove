from __future__ import annotations

import json
import os
import queue
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

MAX_TASKS_KEPT = 50
LABEL_MAX = 90

_FILE_VERBS = {
    "list_directory": "Listing",
    "read_file": "Reading",
    "search_files": "Searching in",
    "make_directory": "Creating folder",
    "write_file": "Writing",
    "move_file": "Moving",
    "copy_file": "Copying",
    "trash_file": "Moving to Trash:",
}

_FIXED_LABELS = {
    "click": "Clicking",
    "type": "Typing",
    "scroll": "Scrolling",
    "keypress": "Pressing keys",
    "screenshot": "Looking at the screen",
    "describe_ui": "Reading the screen layout",
    "get_text": "Reading the page",
    "wait": "Waiting",
    "finish": "Wrapping up",
    "ask_for_help": "Asking for your help",
    "remember": "Saving a note",
}


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LABEL_MAX else text[: LABEL_MAX - 1] + "…"


# Query strings and fragments routinely carry tokens and ids; the preview only needs where we are.
def safe_url(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else url.split("?")[0].split("#")[0]


def _host(url: object) -> str:
    return urlparse(str(url)).netloc or str(url)


# Labels are built from tool name plus a few non-sensitive arguments only. Typed text,
# key sequences and tool results never leave this function, so passwords typed by a
# tool call can't reach the UI.
def describe_tool(name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments) if arguments else {}
    except ValueError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    if name == "open_url":
        return _clip(f"Opening {_host(args.get('url', ''))}")
    if name == "fetch_url":
        return _clip(f"Reading {_host(args.get('url', ''))}")
    if name in ("open_application", "focus_application"):
        verb = "Opening" if name == "open_application" else "Switching to"
        return _clip(f"{verb} {args.get('name', 'an app')}")
    if name in _FILE_VERBS:
        target = args.get("path") or args.get("source") or args.get("root") or ""
        return _clip(f"{_FILE_VERBS[name]} {os.path.basename(str(target).rstrip('/')) or 'a folder'}")
    if name.startswith("delegate_"):
        agent = name.removeprefix("delegate_")
        return _clip(f"{agent.capitalize()} agent: {args.get('subtask', '')}")
    return _FIXED_LABELS.get(name, _clip(name.replace("_", " ").capitalize()))


class ActivityBus:
    # In-process, like paused_runs: per-task event history plus live subscribers, so a
    # client that connects late (or reconnects with ?after=seq) replays what it missed.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._stops: set[str] = set()
        self._frames: dict[str, tuple[bytes, int]] = {}

    def publish(self, task_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            history = self._history.setdefault(task_id, [])
            self._history.move_to_end(task_id)
            while len(self._history) > MAX_TASKS_KEPT:
                dropped, _ = self._history.popitem(last=False)
                self._subscribers.pop(dropped, None)
                self._stops.discard(dropped)
                self._frames.pop(dropped, None)
            event = {**event, "seq": len(history) + 1}
            history.append(event)
            subscribers = list(self._subscribers.get(task_id, []))
        for q in subscribers:
            q.put(event)

    def subscribe(self, task_id: str, after: int = 0) -> tuple[list[dict[str, Any]], queue.Queue]:
        q: queue.Queue = queue.Queue()
        with self._lock:
            backlog = [e for e in self._history.get(task_id, []) if e["seq"] > after]
            self._subscribers.setdefault(task_id, []).append(q)
        return backlog, q

    def unsubscribe(self, task_id: str, q: queue.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(task_id, [])
            if q in subscribers:
                subscribers.remove(q)

    # Latest preview frame per task, memory only (never written to disk).
    def set_frame(self, task_id: str, image: bytes) -> int:
        with self._lock:
            n = self._frames.get(task_id, (b"", 0))[1] + 1
            self._frames[task_id] = (image, n)
            return n

    def get_frame(self, task_id: str) -> bytes | None:
        with self._lock:
            frame = self._frames.get(task_id)
        return frame[0] if frame else None

    def request_stop(self, task_id: str) -> None:
        with self._lock:
            self._stops.add(task_id)

    def stop_requested(self, task_id: str | None) -> bool:
        with self._lock:
            return task_id in self._stops

    def clear_stop(self, task_id: str) -> None:
        with self._lock:
            self._stops.discard(task_id)


class Activity:
    # Per-request handle: bound to the run's task id once the route knows it, passed to
    # the orchestrator as `on_event`, and folded into the cancel check so Stop works.
    def __init__(self, bus: ActivityBus, interrupted: Callable[[], bool]) -> None:
        self._bus = bus
        self._interrupted = interrupted
        self.task_id: str | None = None

    def bind(self, task_id: str) -> None:
        self.task_id = task_id

    def emit(self, event: dict[str, Any]) -> None:
        if self.task_id is None:
            return
        if event.get("type") == "frame":
            event = dict(event)
            event["n"] = self._bus.set_frame(self.task_id, event.pop("image"))
        self._bus.publish(self.task_id, event)

    def cancel_check(self) -> bool:
        return self._interrupted() or self._bus.stop_requested(self.task_id)

    def stopped(self) -> bool:
        return self._bus.stop_requested(self.task_id)

    def clear_stop(self) -> None:
        if self.task_id is not None:
            self._bus.clear_stop(self.task_id)
