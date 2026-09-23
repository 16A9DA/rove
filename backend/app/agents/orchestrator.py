from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from app.agents.base import AgentResult, AgentRuntime

# Each delegate call is its own AgentRuntime with its own independent deadline (see
# AgentRuntime.run) — the orchestrator's own budget must comfortably outlast several
# full-length sub-agent runs, or one slow/rate-limited delegate call can burn through
# the orchestrator's entire timeout before it even gets to react to the result.
ORCHESTRATOR_TIMEOUT_SECONDS = 900.0
from app.controllers import BrowserController, ComputerController, NativeComputerController
from app.memory import MemoryCategory, MemoryService
from app.providers import LLMProvider
from app.tools import FinishParams, Tool, ToolRegistry, ToolRiskLevel, browser_registry, desktop_registry, finish, research_registry

ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are Rove's orchestrator. You never touch the screen yourself — break the "
    "user's goal into subtasks and delegate each to the right specialist: "
    "delegate_browser for anything in a web browser, delegate_desktop for native "
    "macOS applications, delegate_research for reading a URL's content without "
    "opening a browser. If the user names a specific app or site (e.g. \"search on "
    "DuckDuckGo\", \"open TextEdit\"), pass that exact name through in the subtask — "
    "never substitute your own default. After each delegate call, check whether its "
    "result actually satisfies the goal; if not, delegate again with a more specific "
    "subtask or a different agent. Call finish once the whole goal is done. "
    "Use remember to save anything worth recalling on future tasks: personal facts "
    "or preferences about the user (category personal), a notable outcome of this "
    "task (episodic), a reusable way of doing something (workflow), or a durable "
    "fact about their setup/accounts/files (structured). Don't bother for anything "
    "only relevant to this one task."
)

BROWSER_SYSTEM_PROMPT = (
    "You are Rove's browser specialist. Use your tools to complete the subtask "
    "you're given, then call finish. Start with open_url to load a real page — if "
    "the subtask names a specific site (e.g. DuckDuckGo, Wikipedia), go there "
    "directly (e.g. https://duckduckgo.com), don't substitute a different one. "
    "There is no 'navigate' tool, and internal browser pages like chrome:// are not "
    "reachable. Use get_text for cheap reads (it returns the whole page's text, not "
    "just what's visible). Use scroll before a screenshot when what you need to "
    "click or read isn't visible in the current view — screenshot only shows what's "
    "currently on screen. Interact like a person: type into the focused input, "
    "press Return to submit, rather than building query URLs by hand."
)

DESKTOP_SYSTEM_PROMPT = (
    "You are Rove's desktop specialist. Use open_application to launch an app and "
    "focus_application to bring an already-running one to the foreground, then "
    "operate it and call finish. Use screenshot to see dialogs/buttons/layout — "
    "native apps expose no cheap text read — and scroll first if what you need "
    "isn't visible on screen yet, since screenshot only shows the current view. "
    "Save with cmd+s or cmd+shift+s (cmd+shift+g inside the save panel to jump to "
    "a folder); close a single document with cmd+w, never cmd+q."
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
        # Real headed Chrome (BrowserController) is already visible on screen — no need
        # to also open the result in the user's separate default browser on finish.
        return AgentRuntime(provider, browser_registry(browser), _with_memory(BROWSER_SYSTEM_PROMPT))

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

    return AgentRuntime(
        provider, registry, _with_memory(ORCHESTRATOR_SYSTEM_PROMPT), timeout_seconds=ORCHESTRATOR_TIMEOUT_SECONDS
    )
