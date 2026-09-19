from __future__ import annotations

import webbrowser
from typing import Any, Callable

from pydantic import BaseModel

from app.agents.base import AgentResult, AgentRuntime
from app.controllers import BrowserController, ComputerController, NativeComputerController
from app.memory import MemoryCategory, MemoryService
from app.providers import LLMProvider
from app.tools import FinishParams, Tool, ToolRegistry, ToolRiskLevel, browser_registry, desktop_registry, finish, research_registry

ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are Rove's orchestrator. You never touch the screen yourself — break the "
    "user's goal into subtasks and delegate each to the right specialist: "
    "delegate_browser for anything in a web browser, delegate_desktop for native "
    "macOS applications, delegate_research for reading a URL's content without "
    "opening a browser. After each delegate call, check whether its result actually "
    "satisfies the goal; if not, delegate again with a more specific subtask or a "
    "different agent. Call finish once the whole goal is done. "
    "Use remember to save anything worth recalling on future tasks: personal facts "
    "or preferences about the user (category personal), a notable outcome of this "
    "task (episodic), a reusable way of doing something (workflow), or a durable "
    "fact about their setup/accounts/files (structured). Don't bother for anything "
    "only relevant to this one task."
)

BROWSER_SYSTEM_PROMPT = (
    "You are Rove's browser specialist. Use your tools to complete the subtask "
    "you're given, then call finish. Use get_text for cheap reads, screenshot when "
    "you need to see layout. Interact like a person: navigate, type into the "
    "focused input, press Return to submit, rather than building query URLs by hand."
)

DESKTOP_SYSTEM_PROMPT = (
    "You are Rove's desktop specialist. Use your tools to operate native macOS "
    "applications and complete the subtask you're given, then call finish. Use "
    "screenshot to see dialogs/buttons/layout — native apps expose no cheap text "
    "read. Save with cmd+s or cmd+shift+s (cmd+shift+g inside the save panel to "
    "jump to a folder); close a single document with cmd+w, never cmd+q."
)

RESEARCH_SYSTEM_PROMPT = (
    "You are Rove's research specialist. Use fetch_url to read the content needed "
    "for the subtask, then call finish with what you found."
)


class SubtaskParams(BaseModel):
    subtask: str


class RememberParams(BaseModel):
    category: MemoryCategory
    content: str


def _delegate_output(result: AgentResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "result": result.final_message,
        "error": result.error,
    }


def _make_delegate(build_runtime: Callable[[], AgentRuntime]) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, SubtaskParams)
        return _delegate_output(build_runtime().run(params.subtask))

    return handler


def _make_remember(memory: MemoryService) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, RememberParams)
        memory.remember(params.category, params.content)
        return {"remembered": params.content, "category": params.category.value}

    return handler


def orchestrator_runtime(
    provider: LLMProvider,
    browser: BrowserController | None = None,
    native: ComputerController | None = None,
    opener: Callable[[str], object] = webbrowser.open,
    memory: MemoryService | None = None,
) -> AgentRuntime:
    # A fresh sub-AgentRuntime (and message history) is built per delegate call, but
    # the underlying controller is shared across the whole task — a browser tab or
    # native app session opened by one subtask stays open for the next.
    browser = browser if browser is not None else BrowserController()
    native = native if native is not None else NativeComputerController()
    memory = memory if memory is not None else MemoryService()

    # Recalled once per task (not re-queried per delegate call) and handed down to
    # every agent's own prompt read-only — the orchestrator is the only writer, via
    # the remember tool below, so there's one place memory state can change.
    remembered = memory.format_context()

    def _with_memory(prompt: str) -> str:
        return f"{prompt}\n\n{remembered}" if remembered else prompt

    def build_browser_runtime() -> AgentRuntime:
        return AgentRuntime(
            provider,
            browser_registry(browser),
            _with_memory(BROWSER_SYSTEM_PROMPT),
            on_finish=lambda: opener(browser.current_url) if browser.is_launched else None,
        )

    def build_desktop_runtime() -> AgentRuntime:
        return AgentRuntime(provider, desktop_registry(native), _with_memory(DESKTOP_SYSTEM_PROMPT))

    def build_research_runtime() -> AgentRuntime:
        return AgentRuntime(provider, research_registry(), _with_memory(RESEARCH_SYSTEM_PROMPT))

    registry = ToolRegistry()
    registry.register(Tool("delegate_browser", "Delegate a subtask to the browser specialist agent.", SubtaskParams, ToolRiskLevel.LOW, _make_delegate(build_browser_runtime)))
    registry.register(Tool("delegate_desktop", "Delegate a subtask to the native-application specialist agent.", SubtaskParams, ToolRiskLevel.LOW, _make_delegate(build_desktop_runtime)))
    registry.register(Tool("delegate_research", "Delegate a subtask to the research specialist agent (reads a URL without a browser).", SubtaskParams, ToolRiskLevel.LOW, _make_delegate(build_research_runtime)))
    registry.register(Tool("remember", "Save something worth recalling on future tasks.", RememberParams, ToolRiskLevel.LOW, _make_remember(memory)))
    registry.register(Tool("finish", "Report the whole goal as complete with a result.", FinishParams, ToolRiskLevel.LOW, finish))

    return AgentRuntime(provider, registry, _with_memory(ORCHESTRATOR_SYSTEM_PROMPT))
