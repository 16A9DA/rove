from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, Field

from app.controllers.base import ComputerController
from app.help_request import HelpRequest
if TYPE_CHECKING:
    from app.permissions import PermissionGate
from app.tools.base import (
    ASK_FOR_HELP_DESCRIPTION,
    AskForHelpParams,
    EmptyParams,
    FinishParams,
    Tool,
    ToolRegistry,
    ToolRiskLevel,
    WaitParams,
    finish,
    make_ask_for_help,
    wait,
)


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


def _make_open_application(native: ComputerController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ApplicationParams)
        native.open_application(params.name)
        return {"opened": params.name}

    return handler


def _make_focus_application(native: ComputerController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ApplicationParams)
        native.focus_application(params.name)
        return {"focused": params.name}

    return handler


def _make_screenshot(native: ComputerController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, EmptyParams)
        jpeg_bytes = native.screenshot()
        return {"screenshot": "captured", "_image_base64": base64.b64encode(jpeg_bytes).decode("ascii")}

    return handler


def _make_describe_ui(native: ComputerController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, EmptyParams)
        return {"elements": native.describe_ui()}

    return handler


def _label_at(controller, x: int, y: int) -> str | None:
    # A failed lookup must not block or crash the click — the gate just sees no label.
    try:
        return controller.element_at(x, y)
    except Exception:
        return None


def _make_click(native: ComputerController, gate: PermissionGate | None = None) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ClickParams)
        if gate is not None:
            gate.guard("click", {"x": params.x, "y": params.y}, _label_at(native, params.x, params.y))
        native.click(params.x, params.y)
        return {"clicked": [params.x, params.y]}

    return handler


def _make_type(native: ComputerController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, TypeParams)
        native.type(params.text)
        return {"typed": params.text}

    return handler


def _make_scroll(native: ComputerController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ScrollParams)
        native.scroll(params.direction, params.amount)
        return {"scrolled": params.direction, "amount": params.amount}

    return handler


def _make_keypress(native: ComputerController, gate: PermissionGate | None = None) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, KeypressParams)
        if gate is not None:
            gate.guard("keypress", {"keys": params.keys}, None, params.keys)
        native.keypress(params.keys)
        return {"pressed": params.keys}

    return handler


def desktop_registry(native: ComputerController, help_request: HelpRequest, gate: PermissionGate | None = None) -> ToolRegistry:
    # No get_text here: NativeComputerController raises NotImplementedError for it —
    # screenshot is the native-app observation path instead.
    registry = ToolRegistry()
    for tool in (
        Tool("open_application", "Open a native application by name.", ApplicationParams, ToolRiskLevel.LOW, _make_open_application(native)),
        Tool("focus_application", "Bring an already-open application to the foreground.", ApplicationParams, ToolRiskLevel.LOW, _make_focus_application(native)),
        Tool("screenshot", "Capture a screenshot of the current screen.", EmptyParams, ToolRiskLevel.LOW, _make_screenshot(native)),
        Tool(
            "describe_ui",
            "List the frontmost application's visible interactive elements (role, label, exact x/y/width/height, "
            "whether focused). Call this before click/type to get real coordinates instead of guessing from a "
            "screenshot — cheaper and more reliable than vision.",
            EmptyParams,
            ToolRiskLevel.LOW,
            _make_describe_ui(native),
        ),
        Tool("click", "Click at screen coordinates.", ClickParams, ToolRiskLevel.LOW, _make_click(native, gate)),
        Tool("type", "Type text at the current focus.", TypeParams, ToolRiskLevel.LOW, _make_type(native)),
        Tool("scroll", "Scroll the active view.", ScrollParams, ToolRiskLevel.LOW, _make_scroll(native)),
        Tool("keypress", "Send a keyboard shortcut, e.g. 'cmd+t'.", KeypressParams, ToolRiskLevel.LOW, _make_keypress(native, gate)),
        Tool("wait", "Pause for a short duration.", WaitParams, ToolRiskLevel.LOW, wait),
        Tool("ask_for_help", ASK_FOR_HELP_DESCRIPTION, AskForHelpParams, ToolRiskLevel.LOW, make_ask_for_help(help_request)),
        Tool("finish", "Report the subtask as complete with a result.", FinishParams, ToolRiskLevel.LOW, finish),
    ):
        registry.register(tool)
    return registry
