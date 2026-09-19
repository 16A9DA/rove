import json

from app.agent import AgentRuntime
from app.environment import ComputerEnvironment
from app.providers import LLMProviderError, LLMResponse, ToolCall
from tests.test_tools import FakeBrowserController, FakeNativeController


class ScriptedProvider:
    """Returns each response in `responses` in order, one per .complete() call."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    def complete(self, messages, tools=None):
        self.calls.append((messages, tools))
        return self._responses.pop(0)


def _env() -> ComputerEnvironment:
    return ComputerEnvironment(browser=FakeBrowserController(), native=FakeNativeController())


def test_run_executes_tool_call_then_finishes() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="open_application", arguments=json.dumps({"name": "Finder"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="finish", arguments=json.dumps({"result": "done", "success": True}))]),
        ]
    )
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("open Finder")

    assert result.success
    assert result.final_message == "done"
    assert [a.tool_name for a in result.actions] == ["open_application", "finish"]
    assert not any(a.is_error for a in result.actions)


def test_run_returns_direct_answer_when_model_calls_no_tool() -> None:
    provider = ScriptedProvider([LLMResponse(content="no tools needed", tool_calls=[])])
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("say hi")

    assert result.success
    assert result.final_message == "no tools needed"
    assert result.actions == []


def test_run_retries_once_on_parse_failure_then_succeeds() -> None:
    class FlakyProvider:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                raise LLMProviderError("malformed request to Groq", status_code=400)
            return LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="finish", arguments=json.dumps({"result": "done"}))])

    provider = FlakyProvider()
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("do something")

    assert result.success
    assert result.final_message == "done"
    assert provider.call_count == 2


def test_run_does_not_retry_non_parse_failure_errors() -> None:
    class FlakyProvider:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, messages, tools=None):
            self.call_count += 1
            raise LLMProviderError("invalid Groq credentials", status_code=401)

    provider = FlakyProvider()
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("do something")

    assert not result.success
    assert provider.call_count == 1


def test_run_stops_on_provider_error() -> None:
    class FailingProvider:
        def complete(self, messages, tools=None):
            raise LLMProviderError("boom", status_code=502)

    runtime = AgentRuntime(FailingProvider(), environment=_env())

    result = runtime.run("do something")

    assert not result.success
    assert result.error == "boom"


def test_run_stops_at_max_steps_without_finish() -> None:
    # every step calls a real no-op tool (wait) that never finishes the task
    responses = [LLMResponse(content=None, tool_calls=[ToolCall(id=str(i), name="wait", arguments="{}")]) for i in range(3)]
    provider = ScriptedProvider(responses)
    runtime = AgentRuntime(provider, environment=_env(), max_steps=3)

    result = runtime.run("loop forever")

    assert not result.success
    assert "max steps" in result.error
    assert len(result.actions) == 3


def test_run_stops_when_cancelled() -> None:
    provider = ScriptedProvider([LLMResponse(content="unreachable", tool_calls=[])])
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("do something", cancel_check=lambda: True)

    assert not result.success
    assert result.error == "cancelled"
    assert provider.calls == []  # cancelled before ever calling the provider


def test_run_opens_final_url_in_real_browser_after_browser_finish() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="open_url", arguments=json.dumps({"url": "https://example.com"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="finish", arguments=json.dumps({"result": "done"}))]),
        ]
    )
    opened: list[str] = []
    runtime = AgentRuntime(provider, environment=_env(), opener=opened.append)

    runtime.run("look something up")

    assert opened == ["https://example.com"]


def test_run_does_not_open_browser_when_native_only() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="open_application", arguments=json.dumps({"name": "Finder"}))]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="finish", arguments=json.dumps({"result": "done"}))]),
        ]
    )
    opened: list[str] = []
    runtime = AgentRuntime(provider, environment=_env(), opener=opened.append)

    runtime.run("open Finder")

    assert opened == []


def test_run_feeds_screenshot_back_as_image_message() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="screenshot", arguments="{}")]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="finish", arguments=json.dumps({"result": "saw it"}))]),
        ]
    )
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("look at the screen")

    assert result.success
    image_messages = [m for m in provider.calls[1][0] if m["role"] == "user" and isinstance(m["content"], list)]
    assert len(image_messages) == 1
    assert image_messages[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    # the tool-role message itself must stay plain text — no image blocks smuggled in there
    tool_message = next(m for m in provider.calls[1][0] if m["role"] == "tool")
    assert isinstance(tool_message["content"], str)


def test_action_history_never_carries_raw_provider_content() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content="secret reasoning here", tool_calls=[ToolCall(id="1", name="finish", arguments=json.dumps({"result": "ok"}))]),
        ]
    )
    runtime = AgentRuntime(provider, environment=_env())

    result = runtime.run("do something")

    assert all("secret reasoning" not in a.arguments and "secret reasoning" not in a.result for a in result.actions)
