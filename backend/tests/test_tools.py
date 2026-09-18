import json

from app.tools import ToolExecutor, ToolRiskLevel, ToolValidator, default_registry


def _registry():
    return default_registry()


def test_registry_lists_all_initial_tools() -> None:
    names = {tool.name for tool in _registry().list()}
    assert names == {
        "screenshot", "open_url", "open_application", "focus_application",
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


def test_executor_pending_controller_tool() -> None:
    result = ToolExecutor(_registry()).execute("id1", "screenshot", "{}")
    assert result.is_error
    assert "not wired" in result.content


def test_executor_wait_runs() -> None:
    result = ToolExecutor(_registry()).execute("id1", "wait", json.dumps({"seconds": 0}))
    assert not result.is_error
    assert json.loads(result.content) == {"waited": 0}


def test_executor_finish_runs() -> None:
    result = ToolExecutor(_registry()).execute("id1", "finish", json.dumps({"result": "done"}))
    assert not result.is_error
    assert json.loads(result.content) == {"success": True, "result": "done"}
