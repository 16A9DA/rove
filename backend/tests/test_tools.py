import base64
import json

from app.controllers import ComputerController
from app.environment import ComputerEnvironment
from app.tools import ToolExecutor, ToolRiskLevel, ToolValidator, default_registry


class FakeBrowserController(ComputerController):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.launched = False
        self.url: str | None = None

    @property
    def is_launched(self) -> bool:
        return self.launched

    @property
    def current_url(self) -> str | None:
        return self.url

    def launch(self) -> None:
        self.launched = True

    def navigate(self, url: str) -> None:
        self.url = url
        self.calls.append(("navigate", (url,)))

    def screenshot(self) -> bytes:
        return b"fake-browser-png"

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", (x, y)))

    def type(self, text: str) -> None:
        self.calls.append(("type", (text,)))

    def scroll(self, direction: str, amount: int = 3) -> None:
        self.calls.append(("scroll", (direction, amount)))

    def keypress(self, keys: str) -> None:
        self.calls.append(("keypress", (keys,)))

    def open_application(self, name: str) -> None:
        raise NotImplementedError("FakeBrowserController cannot open native applications")

    def focus_application(self, name: str) -> None:
        raise NotImplementedError("FakeBrowserController cannot focus native applications")

    def get_active_application(self) -> str | None:
        return "Chrome" if self.launched else None

    def get_text(self) -> str:
        return "fake browser page text"


class FakeNativeController(ComputerController):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.active_app: str | None = None

    def screenshot(self) -> bytes:
        return b"fake-native-png"

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", (x, y)))

    def type(self, text: str) -> None:
        self.calls.append(("type", (text,)))

    def scroll(self, direction: str, amount: int = 3) -> None:
        self.calls.append(("scroll", (direction, amount)))

    def keypress(self, keys: str) -> None:
        self.calls.append(("keypress", (keys,)))

    def open_application(self, name: str) -> None:
        self.active_app = name
        self.calls.append(("open_application", (name,)))

    def focus_application(self, name: str) -> None:
        self.active_app = name
        self.calls.append(("focus_application", (name,)))

    def get_active_application(self) -> str | None:
        return self.active_app

    def get_text(self) -> str:
        raise NotImplementedError("FakeNativeController cannot extract window text")


def _env() -> ComputerEnvironment:
    return ComputerEnvironment(browser=FakeBrowserController(), native=FakeNativeController())


def _registry():
    return default_registry(_env())


def test_registry_lists_all_initial_tools() -> None:
    names = {tool.name for tool in _registry().list()}
    assert names == {
        "screenshot", "get_text", "open_url", "open_application", "focus_application",
        "click", "type", "scroll", "keypress", "wait", "finish",
    }


def test_to_groq_tools_shape() -> None:
    schemas = _registry().to_groq_tools()
    assert all(s["type"] == "function" for s in schemas)
    assert all("parameters" in s["function"] for s in schemas)


def test_all_initial_tools_are_low_risk() -> None:
    assert all(tool.risk_level == ToolRiskLevel.LOW for tool in _registry().list())


def test_validator_rejects_missing_field() -> None:
    tool = _registry().get("open_url")
    try:
        ToolValidator.validate(tool, {})
        assert False, "expected ToolError"
    except Exception as exc:
        assert "invalid arguments" in str(exc)


def test_validator_rejects_bad_enum() -> None:
    tool = _registry().get("scroll")
    try:
        ToolValidator.validate(tool, {"direction": "sideways"})
        assert False, "expected ToolError"
    except Exception as exc:
        assert "invalid arguments" in str(exc)


def test_executor_unknown_tool() -> None:
    result = ToolExecutor(_registry()).execute("id1", "does_not_exist", "{}")
    assert result.is_error
    assert "unknown tool" in result.content


def test_executor_malformed_arguments() -> None:
    result = ToolExecutor(_registry()).execute("id1", "wait", "{not json")
    assert result.is_error
    assert "malformed arguments" in result.content


def test_executor_validation_error() -> None:
    result = ToolExecutor(_registry()).execute("id1", "click", json.dumps({"x": 1}))
    assert result.is_error
    assert "invalid arguments" in result.content


def test_executor_wait_runs() -> None:
    result = ToolExecutor(_registry()).execute("id1", "wait", json.dumps({"seconds": 0}))
    assert not result.is_error
    assert json.loads(result.content) == {"waited": 0}


def test_executor_finish_runs() -> None:
    result = ToolExecutor(_registry()).execute("id1", "finish", json.dumps({"result": "done"}))
    assert not result.is_error
    assert json.loads(result.content) == {"success": True, "result": "done"}


def test_open_url_launches_browser_and_activates_it() -> None:
    env = _env()
    result = ToolExecutor(default_registry(env)).execute("id1", "open_url", json.dumps({"url": "https://example.com"}))

    assert not result.is_error
    assert env.browser.launched
    assert env.browser.url == "https://example.com"
    assert env.active is env.browser


def test_open_application_activates_native() -> None:
    env = _env()
    env.active = env.browser  # start pointed at the browser, to prove open_application switches it
    result = ToolExecutor(default_registry(env)).execute("id1", "open_application", json.dumps({"name": "Finder"}))

    assert not result.is_error
    assert env.native.active_app == "Finder"
    assert env.active is env.native


def test_click_targets_active_controller() -> None:
    env = _env()
    env.open_url("https://example.com")  # activates the browser
    result = ToolExecutor(default_registry(env)).execute("id1", "click", json.dumps({"x": 5, "y": 6}))

    assert not result.is_error
    assert ("click", (5, 6)) in env.browser.calls
    assert not env.native.calls


def test_screenshot_returns_base64_from_active_controller() -> None:
    env = _env()
    result = ToolExecutor(default_registry(env)).execute("id1", "screenshot", "{}")

    assert not result.is_error
    payload = json.loads(result.content)
    assert base64.b64decode(payload["screenshot_base64"]) == b"fake-native-png"


def test_get_text_returns_text_from_active_controller() -> None:
    env = _env()
    env.open_url("http://example.com")

    result = ToolExecutor(default_registry(env)).execute("id1", "get_text", "{}")

    assert not result.is_error
    assert json.loads(result.content)["text"] == "fake browser page text"


def test_executor_turns_notimplementederror_into_error_result() -> None:
    # a controller legitimately not supporting an action shouldn't crash the executor
    from app.tools import EmptyParams, Tool

    def _unsupported(_params) -> dict:
        raise NotImplementedError("not supported here")

    registry = default_registry(_env())
    registry.register(Tool("unsupported_action", "test-only", EmptyParams, ToolRiskLevel.LOW, _unsupported))

    result = ToolExecutor(registry).execute("id1", "unsupported_action", "{}")
    assert result.is_error
    assert "not supported here" in result.content


def test_executor_blocks_non_low_risk_tools() -> None:
    from app.tools import EmptyParams, Tool

    registry = default_registry(_env())
    registry.register(Tool("dangerous_action", "test-only", EmptyParams, ToolRiskLevel.HIGH, lambda _params: {}))

    result = ToolExecutor(registry).execute("id1", "dangerous_action", "{}")
    assert result.is_error
    assert "requires permission approval" in result.content
