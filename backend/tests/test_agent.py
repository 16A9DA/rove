from fastapi.testclient import TestClient

from app.agent import ActionSummary, AgentResult
from app.main import app, get_agent_runtime, get_provider
from app.providers import LLMProviderError, LLMResponse, ToolCall

client = TestClient(app)


class FakeProvider:
    def __init__(self, response=None, error: LLMProviderError | None = None) -> None:
        self._response = response
        self._error = error

    def complete(self, messages, tools=None):
        if self._error:
            raise self._error
        return self._response


def _override(provider) -> None:
    app.dependency_overrides[get_provider] = lambda: provider


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_agent_message_success() -> None:
    _override(FakeProvider(response=LLMResponse(content="hi there", tool_calls=[ToolCall(id="1", name="open_app", arguments="{}")])))

    response = client.post("/api/agent/message", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "hi there"
    assert body["tool_calls"] == [{"id": "1", "name": "open_app", "arguments": "{}"}]


def test_agent_message_invalid_credentials() -> None:
    _override(FakeProvider(error=LLMProviderError("invalid Groq credentials", status_code=401)))

    response = client.post("/api/agent/message", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 401


def test_agent_message_timeout() -> None:
    _override(FakeProvider(error=LLMProviderError("Groq request timed out", status_code=504)))

    response = client.post("/api/agent/message", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 504


def test_agent_message_malformed_response() -> None:
    _override(FakeProvider(error=LLMProviderError("malformed response from Groq", status_code=502)))

    response = client.post("/api/agent/message", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 502


class FakeRuntime:
    def __init__(self, result: AgentResult) -> None:
        self._result = result

    def run(self, goal: str, cancel_check=None) -> AgentResult:
        return self._result


def test_agent_run_success() -> None:
    result = AgentResult(
        task_id="task-1",
        success=True,
        final_message="done",
        actions=[ActionSummary(tool_name="finish", arguments="{}", result='{"result": "done"}', is_error=False)],
    )
    app.dependency_overrides[get_agent_runtime] = lambda: FakeRuntime(result)

    response = client.post("/api/agent/run", json={"goal": "do something"})

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "task-1"
    assert body["success"] is True
    assert body["final_message"] == "done"
    assert body["actions"][0]["tool_name"] == "finish"


def test_agent_message_provider_failure() -> None:
    _override(FakeProvider(error=LLMProviderError("Groq API error (500)", status_code=502)))

    response = client.post("/api/agent/message", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 502
