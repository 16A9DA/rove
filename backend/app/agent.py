from __future__ import annotations

import json
import logging
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Callable

from app.environment import ComputerEnvironment
from app.providers import LLMProvider, LLMProviderError
from app.tools import ToolExecutor, ToolRegistry, default_registry

logger = logging.getLogger("rove.agent")

DEFAULT_MAX_STEPS = 20
DEFAULT_TIMEOUT_SECONDS = 120.0
# malformed-request (400) responses from the provider are usually a one-off tool-call
# parse failure on the model's side, not a bad request on ours — worth one retry before
# giving up. Other status codes (auth, rate-limit, timeout) are not retried here.
PARSE_FAILURE_RETRY_ATTEMPTS = 1

SYSTEM_PROMPT = (
    "You are Rove, an AI that operates the user's computer through the available tools. "
    "Use tools to accomplish the user's goal, then call finish with the result. "
    "Use get_text to read what is on screen — you have no way to see screenshots. "
    "Interact like a person would: navigate to a page, type into its focused input, "
    "then press Return to submit, rather than building search/query URLs by hand. "
    "Opening an application does not guarantee an editable document is focused — "
    "if typing needs a document (e.g. a text editor), create/focus one first "
    "(e.g. a New Document keypress) before typing into it."
)


@dataclass
class ActionSummary:
    # Safe, user-facing record of one executed tool call — never raw model reasoning.
    tool_name: str
    arguments: str
    result: str
    is_error: bool


@dataclass
class AgentResult:
    task_id: str
    success: bool
    final_message: str | None
    actions: list[ActionSummary] = field(default_factory=list)
    error: str | None = None


class AgentRuntime:
    def __init__(
        self,
        provider: LLMProvider,
        environment: ComputerEnvironment | None = None,
        registry: ToolRegistry | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[[str], object] = webbrowser.open,
    ) -> None:
        self._provider = provider
        self._environment = environment or ComputerEnvironment()
        self._registry = registry or default_registry(self._environment)
        self._executor = ToolExecutor(self._registry)
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def run(self, goal: str, cancel_check: Callable[[], bool] | None = None) -> AgentResult:
        task_id = str(uuid.uuid4())
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": goal},
        ]
        actions: list[ActionSummary] = []
        deadline = time.monotonic() + self._timeout_seconds

        for step in range(self._max_steps):
            if cancel_check is not None and cancel_check():
                return AgentResult(task_id, False, None, actions, error="cancelled")
            if time.monotonic() > deadline:
                return AgentResult(task_id, False, None, actions, error="timed out")

            response = None
            for attempt in range(PARSE_FAILURE_RETRY_ATTEMPTS + 1):
                try:
                    response = self._provider.complete(messages, tools=self._registry.to_groq_tools())
                    break
                except LLMProviderError as exc:
                    logger.warning("agent step %d attempt %d: provider error: %s", step, attempt, exc)
                    if exc.status_code != 400 or attempt == PARSE_FAILURE_RETRY_ATTEMPTS:
                        return AgentResult(task_id, False, None, actions, error=str(exc))
            assert response is not None

            if not response.tool_calls:
                # model answered directly instead of calling finish — treat as done
                return AgentResult(task_id, True, response.content, actions)

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                        for tc in response.tool_calls
                    ],
                }
            )

            for tool_call in response.tool_calls:
                result = self._executor.execute(tool_call.id, tool_call.name, tool_call.arguments)
                actions.append(ActionSummary(tool_call.name, tool_call.arguments, result.content, result.is_error))
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result.content})

                if tool_call.name == "finish" and not result.is_error:
                    payload = json.loads(result.content)
                    self._show_browser_result()
                    return AgentResult(task_id, payload.get("success", True), payload.get("result"), actions)

        return AgentResult(task_id, False, None, actions, error=f"exceeded max steps ({self._max_steps})")

    def _show_browser_result(self) -> None:
        browser = self._environment.browser
        if self._environment.active is browser and browser.is_launched:
            self._opener(browser.current_url)
