from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass

from app.help_request import HelpRequest
from app.tools.base import ToolError

# Consequence terms: matched against the label of the control being clicked (or the form an
# Enter would submit), never against anything the model wrote — it can't talk its way past this.
HIGH_RISK = re.compile(
    r"\b(send|submit|buy|purchase|pay|place (?:your )?order|checkout|check out|confirm (?:order|purchase|payment)|"
    r"delete|remove|erase|empty trash|transfer|wire|donate|subscribe|publish|post|sign out|log out|unsubscribe)\b",
    re.I,
)
# Shortcuts that commit regardless of what has focus: send in mail/chat clients, delete files.
HIGH_RISK_KEYS = {"cmd+return", "cmd+enter", "cmd+shift+d", "cmd+backspace", "cmd+delete", "cmd+shift+backspace"}


@dataclass
class Approval:
    fingerprint: str
    tool: str
    summary: str


# In-process like paused_runs: a pending approval has to survive from the request that hit
# it to the /resume request that answers it.
_lock = threading.Lock()
_pending: dict[str, Approval] = {}
_granted: dict[str, set[str]] = {}
_denied: dict[str, set[str]] = {}
audit_sink: Callable[[str, str, str, str], None] | None = None  # (task_id, tool, summary, decision)


def pending(task_id: str) -> Approval | None:
    with _lock:
        return _pending.get(task_id)


def resolve(task_id: str, approve: bool) -> Approval | None:
    with _lock:
        approval = _pending.pop(task_id, None)
        if approval is not None:
            (_granted if approve else _denied).setdefault(task_id, set()).add(approval.fingerprint)
            if audit_sink is not None:
                audit_sink(task_id, approval.tool, approval.summary, "approved" if approve else "denied")
        return approval


def _fingerprint(tool: str, args: dict) -> str:
    return f"{tool}:{json.dumps(args, sort_keys=True)}"


def classify(tool: str, label: str | None, keys: str | None = None) -> bool:
    if tool == "keypress" and keys:
        normalized = keys.lower().replace(" ", "")
        if normalized in HIGH_RISK_KEYS:
            return True
    return bool(label and HIGH_RISK.search(label))


class PermissionGate:
    # Per-request, like HelpRequest: the route binds the task id; handlers call guard() before
    # acting. A risky call raises ToolError (so it never executes), records a pending approval
    # and asks via the existing help-request pause — the user answers through /api/agent/resume.
    def __init__(self, help_request: HelpRequest) -> None:
        self._help_request = help_request
        self.task_id: str | None = None

    def bind(self, task_id: str) -> None:
        self.task_id = task_id

    def guard(self, tool: str, args: dict, label: str | None, keys: str | None = None) -> None:
        if classify(tool, label, keys):
            self.require(tool, args, f"{tool} {label!r}" if label else f"{tool} {keys}")

    # Unconditional: used where the operation itself (not a label) is the risk, e.g. trashing a file.
    def require(self, tool: str, args: dict, summary: str) -> None:
        task_id = self.task_id or ""
        fp = _fingerprint(tool, args)
        with _lock:
            if fp in _granted.get(task_id, set()):
                _granted[task_id].discard(fp)
                return
            denied = fp in _denied.get(task_id, set())
        if denied:
            raise ToolError(f"The user denied this action ({summary}). Do not attempt it again; choose another way or finish.")
        with _lock:
            _pending[task_id] = Approval(fp, tool, summary)
        self._help_request.ask(f"Rove wants to {summary}. Approve or cancel?")
        raise ToolError(f"Blocked: {summary} needs the user's approval. Stop and wait; do not try another way around it.")
