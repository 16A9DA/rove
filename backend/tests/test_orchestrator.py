import json

from app.agents import orchestrator_runtime
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
    opened: list[str] = []
    runtime = orchestrator_runtime(provider, browser=browser, native=FakeNativeController(), opener=opened.append)

    result = runtime.run("open example.com")

    assert result.success
    assert result.final_message == "done"
    assert [a.tool_name for a in result.actions] == ["delegate_browser", "finish"]
    assert not result.actions[0].is_error
    assert json.loads(result.actions[0].result) == {"success": True, "result": "opened it", "error": None}
    assert browser.url == "https://example.com"
    assert opened == ["https://example.com"]


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

    assert names == {"delegate_browser", "delegate_desktop", "delegate_research", "finish"}
