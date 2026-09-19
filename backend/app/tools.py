from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from app.environment import ComputerEnvironment

logger = logging.getLogger("rove.tools")

MAX_WAIT_SECONDS = 30.0


class ToolRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolError(Exception):
    """Raised when a tool call cannot be validated or executed."""


class EmptyParams(BaseModel):
    pass


class OpenUrlParams(BaseModel):
    url: str


class ApplicationParams(BaseModel):
    name: str


class ClickParams(BaseModel):
    x: int
    y: int


class TypeParams(BaseModel):
    text: str


class ScrollParams(BaseModel):
    direction: str = Field(pattern="^(up|down|left|right)$")
    amount: int = 3


class KeypressParams(BaseModel):
    keys: str


class WaitParams(BaseModel):
    seconds: float = 1.0


class FinishParams(BaseModel):
    result: str
    success: bool = True


def _make_get_text(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, EmptyParams)
        return {"text": env.active.get_text()}

    return handler


def _make_open_url(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, OpenUrlParams)
        env.open_url(params.url)
        return {"url": params.url}

    return handler


def _make_open_application(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ApplicationParams)
        env.open_application(params.name)
        return {"opened": params.name}

    return handler


def _make_focus_application(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ApplicationParams)
        env.focus_application(params.name)
        return {"focused": params.name}

    return handler


def _make_click(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ClickParams)
        env.active.click(params.x, params.y)
        return {"clicked": [params.x, params.y]}

    return handler


def _make_type(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, TypeParams)
        env.active.type(params.text)
        return {"typed": params.text}

    return handler


def _make_scroll(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ScrollParams)
        env.active.scroll(params.direction, params.amount)
        return {"scrolled": params.direction, "amount": params.amount}

    return handler


def _make_keypress(env: ComputerEnvironment) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, KeypressParams)
        env.active.keypress(params.keys)
        return {"pressed": params.keys}

    return handler


def _wait(params: BaseModel) -> dict[str, Any]:
    # Tool.handler is typed as BaseModel -> dict so any handler fits the dataclass field;
    # narrow back to the real params type here (safe, ToolValidator already validated it).
    assert isinstance(params, WaitParams)
    seconds = min(params.seconds, MAX_WAIT_SECONDS)
    time.sleep(seconds)
    return {"waited": seconds}


def _finish(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, FinishParams)
    return {"success": params.success, "result": params.result}


@dataclass
class Tool:
    name: str
    description: str
    params_model: type[BaseModel]
    risk_level: ToolRiskLevel
    handler: Callable[[BaseModel], dict[str, Any]]

    def to_schema(self) -> dict[str, Any]:
        # Matches the OpenAI/Groq function-calling tool format, so this can be
        # passed straight into GroqProvider.complete(tools=...).
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.params_model.model_json_schema(),
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def to_groq_tools(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]


class ToolValidator:
    @staticmethod
    def validate(tool: Tool, arguments: dict[str, Any]) -> BaseModel:
        try:
            return tool.params_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError(f"invalid arguments for {tool.name}: {exc}") from exc


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, tool_call_id: str, name: str, raw_arguments: str) -> ToolResult:
        tool = self._registry.get(name)
        if tool is None:
            return ToolResult(tool_call_id, name, f"unknown tool: {name}", is_error=True)

        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            return ToolResult(tool_call_id, name, f"malformed arguments: {exc}", is_error=True)

        try:
            params = ToolValidator.validate(tool, arguments)
        except ToolError as exc:
            return ToolResult(tool_call_id, name, str(exc), is_error=True)

        # no real permission/confirmation system exists yet — block anything above LOW
        # outright rather than silently letting it run unconfirmed.
        if tool.risk_level != ToolRiskLevel.LOW:
            return ToolResult(tool_call_id, name, f"{name} requires permission approval (not implemented yet)", is_error=True)

        try:
            output = tool.handler(params)
        except NotImplementedError as exc:
            # a controller legitimately doesn't support this action (e.g. BrowserController
            # has no concept of open_application) — a normal error result, not a crash
            return ToolResult(tool_call_id, name, str(exc), is_error=True)
        except Exception as exc:
            logger.warning("tool %s failed: %s", name, exc)
            return ToolResult(tool_call_id, name, f"tool execution failed: {exc}", is_error=True)

        return ToolResult(tool_call_id, name, json.dumps(output))


def default_registry(env: ComputerEnvironment) -> ToolRegistry:
    # All LOW for now: none of these touch files/email/money. MEDIUM/HIGH land with
    # the permission system (phase 18) once file-op and account-changing tools exist.
    registry = ToolRegistry()
    for tool in (
        Tool("get_text", "Read the visible text of the current page/window.", EmptyParams, ToolRiskLevel.LOW, _make_get_text(env)),
        Tool("open_url", "Navigate the browser to a URL.", OpenUrlParams, ToolRiskLevel.LOW, _make_open_url(env)),
        Tool("open_application", "Open a native application by name.", ApplicationParams, ToolRiskLevel.LOW, _make_open_application(env)),
        Tool("focus_application", "Bring an already-open application to the foreground.", ApplicationParams, ToolRiskLevel.LOW, _make_focus_application(env)),
        Tool("click", "Click at screen coordinates.", ClickParams, ToolRiskLevel.LOW, _make_click(env)),
        Tool("type", "Type text at the current focus.", TypeParams, ToolRiskLevel.LOW, _make_type(env)),
        Tool("scroll", "Scroll the active view.", ScrollParams, ToolRiskLevel.LOW, _make_scroll(env)),
        Tool("keypress", "Send a keyboard shortcut, e.g. 'cmd+t'.", KeypressParams, ToolRiskLevel.LOW, _make_keypress(env)),
        Tool("wait", "Pause for a short duration.", WaitParams, ToolRiskLevel.LOW, _wait),
        Tool("finish", "Report the task as complete with a result.", FinishParams, ToolRiskLevel.LOW, _finish),
    ):
        registry.register(tool)
    return registry
