from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

from app.stt import SpeechToTextProvider, STTError

log = logging.getLogger(__name__)

DISMISS_SECONDS = 6.0


class QuickCommand:
    # Drives the Command-hold popover: idle -> listening -> transcribing -> executing -> complete | error.
    # Subscribers (the SSE route) get every state change; the run itself is one blocking call, so
    # "executing" covers the whole agent run until per-step activity events exist.
    def __init__(self, stt: SpeechToTextProvider, run_goal: Callable[[str], tuple[bool, str]]) -> None:
        self._stt = stt
        self._run_goal = run_goal
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._state = {"state": "idle", "message": ""}
        self._busy = False
        self._dismiss: threading.Timer | None = None

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
            q.put(dict(self._state))
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _set(self, state: str, message: str = "") -> None:
        with self._lock:
            if self._dismiss is not None:
                self._dismiss.cancel()
                self._dismiss = None
            self._state = {"state": state, "message": message}
            subscribers = list(self._subscribers)
            if state in ("complete", "error"):
                self._dismiss = threading.Timer(DISMISS_SECONDS, self._set, args=("idle",))
                self._dismiss.start()
        for q in subscribers:
            q.put({"state": state, "message": message})

    def on_hold(self) -> None:
        with self._lock:
            if self._busy:
                return
            self._busy = True
        try:
            self._stt.start_recording()
        except STTError as exc:
            self._busy = False
            self._set("error", str(exc))
            return
        self._set("listening", "Listening...")

    def on_release(self) -> None:
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self) -> None:
        if self._state["state"] != "listening":
            return
        try:
            self._set("transcribing", "Transcribing...")
            try:
                transcript = self._stt.stop_recording().strip()
            except STTError as exc:
                self._set("error", str(exc))
                return
            if not transcript:
                self._set("error", "Didn't catch that.")
                return
            self._set("executing", transcript)
            try:
                ok, message = self._run_goal(transcript)
            except Exception as exc:
                log.warning("quick command run failed: %s", type(exc).__name__)
                self._set("error", "Something went wrong.")
                return
            self._set("complete" if ok else "error", message or ("Done." if ok else "Failed."))
        finally:
            self._busy = False
