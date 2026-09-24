from __future__ import annotations

import threading


class HelpRequest:
    """Per-task flag an `ask_for_help` tool call sets when a sub-agent hits something
    it can't resolve itself (CAPTCHA, login wall, ambiguous instruction). Folded into
    the same `cancel_check` an input interrupt uses, so the run pauses (state saved,
    resumable) the same way — just with the question carried along for the user."""

    def __init__(self) -> None:
        self._question: str | None = None
        self._lock = threading.Lock()

    def ask(self, question: str) -> None:
        with self._lock:
            self._question = question

    def pending(self) -> bool:
        return self._question is not None

    def question(self) -> str | None:
        return self._question
