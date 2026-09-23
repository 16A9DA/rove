import json

from app.tools import EmptyParams, FinishParams, Tool, ToolExecutor, ToolRegistry, ToolRiskLevel, ToolValidator, WaitParams, finish, wait


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("wait", "Pause.", WaitParams, ToolRiskLevel.LOW, wait))
    registry.register(Tool("finish", "Finish.", FinishParams, ToolRiskLevel.LOW, finish))
    return registry


def test_to_openai_tools_shape() -> None:
    schemas = _registry().to_openai_tools()
    assert all(s["type"] == "function" for s in schemas)
    assert all("parameters" in s["function"] for s in schemas)


def test_validator_rejects_missing_field() -> None:
    tool = _registry().get("finish")
    try:
        ToolValidator.validate(tool, {})
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
    result = ToolExecutor(_registry()).execute("id1", "finish", json.dumps({}))
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


def test_executor_turns_notimplementederror_into_error_result() -> None:
    # a controller legitimately not supporting an action shouldn't crash the executor
    def _unsupported(_params) -> dict:
        raise NotImplementedError("not supported here")

    registry = _registry()
    registry.register(Tool("unsupported_action", "test-only", EmptyParams, ToolRiskLevel.LOW, _unsupported))

    result = ToolExecutor(registry).execute("id1", "unsupported_action", "{}")
    assert result.is_error
    assert "not supported here" in result.content


def test_executor_blocks_non_low_risk_tools() -> None:
    registry = _registry()
    registry.register(Tool("dangerous_action", "test-only", EmptyParams, ToolRiskLevel.HIGH, lambda _params: {}))

    result = ToolExecutor(registry).execute("id1", "dangerous_action", "{}")
    assert result.is_error
    assert "requires permission approval" in result.content
