import json

from app.agents import orchestrator_runtime
from app.memory import MemoryCategory, MemoryService
from app.providers import LLMResponse, ToolCall
from tests.conftest import FakeBrowserController, FakeNativeController


class ScriptedProvider:
    """Returns each response in `responses` in order, one per .complete() call —
    shared across the orchestrator and whichever sub-agent it delegates to, since
    they're all driven by the same provider in production too."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages, tools=None):
        self.calls.append(messages)
        return self._responses.pop(0)


def test_delegate_browser_runs_sub_agent_and_folds_result_back() -> None:
    provider = ScriptedProvider(
        [
            # orchestrator delegates to the browser specialist
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="delegate_browser", arguments=json.dumps({"subtask": "open example.com"}))]),
            # browser sub-agent: navigate then finish
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="open_url", arguments=json.dumps({"url": "https://example.com"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="3", name="finish", arguments=json.dumps({"result": "opened it"}))]),
            # orchestrator sees the subtask succeeded, finishes the whole goal
            LLMResponse(content=None, tool_calls=[ToolCall(id="4", name="finish", arguments=json.dumps({"result": "done"}))]),
        ]
    )
    browser = FakeBrowserController()
    runtime = orchestrator_runtime(provider, browser=browser, native=FakeNativeController())

    result = runtime.run("open example.com")

    assert result.success
    assert result.final_message == "done"
    assert [a.tool_name for a in result.actions] == ["delegate_browser", "finish"]
    assert not result.actions[0].is_error
    assert json.loads(result.actions[0].result) == {"success": True, "result": "opened it", "error": None}
    assert browser.url == "https://example.com"


def test_delegate_desktop_runs_sub_agent() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="delegate_desktop", arguments=json.dumps({"subtask": "open Finder"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="open_application", arguments=json.dumps({"name": "Finder"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="3", name="finish", arguments=json.dumps({"result": "opened Finder"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="4", name="finish", arguments=json.dumps({"result": "done"}))]),
        ]
    )
    native = FakeNativeController()
    runtime = orchestrator_runtime(provider, browser=FakeBrowserController(), native=native)

    result = runtime.run("open Finder")

    assert result.success
    assert native.active_app == "Finder"


def test_orchestrator_never_registers_raw_screen_tools() -> None:
    runtime = orchestrator_runtime(ScriptedProvider([]), browser=FakeBrowserController(), native=FakeNativeController())

    names = {tool.name for tool in runtime._registry.list()}

    assert names == {"delegate_browser", "delegate_desktop", "delegate_research", "remember", "finish"}


def test_remember_writes_to_memory_service(tmp_path) -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="remember", arguments=json.dumps({"category": "personal", "content": "likes dark mode"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="finish", arguments=json.dumps({"result": "done"}))]),
        ]
    )
    memory = MemoryService(tmp_path / "test.db")
    runtime = orchestrator_runtime(provider, browser=FakeBrowserController(), native=FakeNativeController(), memory=memory)

    result = runtime.run("remember I like dark mode")

    assert result.success
    assert memory.recall() == [("personal", "likes dark mode")]


def test_recalled_memory_is_injected_into_orchestrator_and_sub_agent_prompts(tmp_path) -> None:
    memory = MemoryService(tmp_path / "test.db")
    memory.remember(MemoryCategory.PERSONAL, "likes dark mode")
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="delegate_browser", arguments=json.dumps({"subtask": "open example.com"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="finish", arguments=json.dumps({"result": "opened it"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="3", name="finish", arguments=json.dumps({"result": "done"}))]),
        ]
    )
    runtime = orchestrator_runtime(provider, browser=FakeBrowserController(), native=FakeNativeController(), memory=memory)

    runtime.run("open example.com")

    orchestrator_system_message = provider.calls[0][0]
    sub_agent_system_message = provider.calls[1][0]
    assert "likes dark mode" in orchestrator_system_message["content"]
    assert "likes dark mode" in sub_agent_system_message["content"]
