from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

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


class WaitParams(BaseModel):
    seconds: float = 1.0


class FinishParams(BaseModel):
    result: str
    success: bool = True


def wait(params: BaseModel) -> dict[str, Any]:
    # Tool.handler is typed as BaseModel -> dict so any handler fits the dataclass field;
    # narrow back to the real params type here (safe, ToolValidator already validated it).
    assert isinstance(params, WaitParams)
    seconds = min(params.seconds, MAX_WAIT_SECONDS)
    time.sleep(seconds)
    return {"waited": seconds}


def finish(params: BaseModel) -> dict[str, Any]:
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
    image_base64: str | None = None


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

        image_base64 = output.pop("_image_base64", None)
        return ToolResult(tool_call_id, name, json.dumps(output), image_base64=image_base64)
