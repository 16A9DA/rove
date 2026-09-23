from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.providers import LLMProvider, LLMProviderError
from app.tools import ToolExecutor, ToolRegistry

logger = logging.getLogger("rove.agent")

DEFAULT_MAX_STEPS = 20
# ponytail: flat constant, not measured per-model. Vision round-trips (image upload +
# inference) run noticeably slower than text-only steps — raise further if screenshot-heavy
# goals still time out, or make this model-aware if that becomes common.
DEFAULT_TIMEOUT_SECONDS = 240.0
# Retried once each: 400 is usually a one-off tool-call parse failure on the model's
# side; 429/503 are transient rate-limit/overload that can clear within a step. 401/504/
# other 502s are not retried here — they're not going to resolve within one agent step.
STEP_RETRY_ATTEMPTS = 1
RETRYABLE_STATUS_CODES = {400, 429, 503}
STEP_RETRY_BACKOFF_SECONDS = 2.0


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
    """Generic tool-calling loop. Reused as-is for the Orchestrator and every
    specialist sub-agent — what differs between them is only the system prompt
    and tool registry passed in, not the loop itself."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        system_prompt: str,
        max_steps: int = DEFAULT_MAX_STEPS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system_prompt = system_prompt
        self._executor = ToolExecutor(registry)
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds
        self._on_finish = on_finish

    def run(self, goal: str, cancel_check: Callable[[], bool] | None = None) -> AgentResult:
        """Drive the tool-calling loop until the model calls `finish`, answers with no
        tool calls, or a stop condition (cancel/timeout/max_steps/provider error) fires.

        Each iteration: send the full message history + tool schemas to the provider,
        run any tool calls it asks for, append their results back into the history, repeat.
        `messages` is the actual conversation state the model sees — every append here
        is permanent context for the rest of the run, which is why screenshots get
        trimmed down to the latest one instead of just accumulating.
        """
        task_id = str(uuid.uuid4())
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
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
            for attempt in range(STEP_RETRY_ATTEMPTS + 1):
                try:
                    response = self._provider.complete(messages, tools=self._registry.to_groq_tools())
                    break
                except LLMProviderError as exc:
                    logger.warning("agent step %d attempt %d: provider error: %s", step, attempt, exc)
                    if exc.status_code not in RETRYABLE_STATUS_CODES or attempt == STEP_RETRY_ATTEMPTS:
                        return AgentResult(task_id, False, None, actions, error=str(exc))
                    if exc.status_code != 400:
                        time.sleep(STEP_RETRY_BACKOFF_SECONDS)
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
                if result.image_base64:
                    # Every step resends the full message list, so old screenshots left in
                    # place would compound request size/latency step after step. Only the
                    # latest one is ever useful — drop earlier ones down to a text stub.
                    for old_message in messages:
                        if old_message.get("role") == "user" and isinstance(old_message.get("content"), list):
                            old_message["content"] = "[earlier screenshot omitted]"
                    # Groq tool-role messages are text-only — the screenshot rides in as its
                    # own user message right after so the model can see it next turn.
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Screenshot from the screenshot tool call above:"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{result.image_base64}"}},
                            ],
                        }
                    )

                if tool_call.name == "finish" and not result.is_error:
                    payload = json.loads(result.content)
                    if self._on_finish is not None:
                        self._on_finish()
                    return AgentResult(task_id, payload.get("success", True), payload.get("result"), actions)

        return AgentResult(task_id, False, None, actions, error=f"exceeded max steps ({self._max_steps})")
