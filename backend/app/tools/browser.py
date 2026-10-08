from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, Field

from app.controllers.browser import BrowserController
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


class OpenUrlParams(BaseModel):
    url: str


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


def _make_open_url(browser: BrowserController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, OpenUrlParams)
        if not browser.is_launched:
            browser.launch()
        browser.navigate(params.url)
        return {"url": params.url}

    return handler


def _make_get_text(browser: BrowserController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, EmptyParams)
        return {"text": browser.get_text()}

    return handler


def _make_screenshot(browser: BrowserController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, EmptyParams)
        jpeg_bytes = browser.screenshot()
        # "_image_base64" is stripped out by ToolExecutor before the JSON tool-result
        # content is built — it rides along on ToolResult.image_base64 instead, so the
        # agent loop can attach it as an image_url block on a separate user message
        # (a Groq tool-role message must be plain text).
        return {"screenshot": "captured", "_image_base64": base64.b64encode(jpeg_bytes).decode("ascii")}

    return handler


def _label_at(controller, x: int, y: int) -> str | None:
    # A failed lookup must not block or crash the click — the gate just sees no label.
    try:
        return controller.element_at(x, y)
    except Exception:
        return None


def _make_click(browser: BrowserController, gate: PermissionGate | None = None) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ClickParams)
        if gate is not None:
            gate.guard("click", {"x": params.x, "y": params.y}, _label_at(browser, params.x, params.y))
        browser.click(params.x, params.y)
        return {"clicked": [params.x, params.y]}

    return handler


def _make_type(browser: BrowserController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, TypeParams)
        browser.type(params.text)
        return {"typed": params.text}

    return handler


def _make_scroll(browser: BrowserController) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, ScrollParams)
        browser.scroll(params.direction, params.amount)
        return {"scrolled": params.direction, "amount": params.amount}

    return handler


def _make_keypress(browser: BrowserController, gate: PermissionGate | None = None) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, KeypressParams)
        if gate is not None:
            hint = browser.focused_form_hint() if params.keys.lower() in ("return", "enter") and browser.is_launched else None
            gate.guard("keypress", {"keys": params.keys}, hint, params.keys)
        browser.keypress(params.keys)
        return {"pressed": params.keys}

    return handler


def browser_registry(browser: BrowserController, help_request: HelpRequest, gate: PermissionGate | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        Tool("open_url", "Navigate the browser to a URL.", OpenUrlParams, ToolRiskLevel.LOW, _make_open_url(browser)),
        Tool("get_text", "Read the visible text of the current page.", EmptyParams, ToolRiskLevel.LOW, _make_get_text(browser)),
        Tool("screenshot", "Capture a screenshot of the current page.", EmptyParams, ToolRiskLevel.LOW, _make_screenshot(browser)),
        Tool("click", "Click at page coordinates.", ClickParams, ToolRiskLevel.LOW, _make_click(browser, gate)),
        Tool("type", "Type text at the current focus.", TypeParams, ToolRiskLevel.LOW, _make_type(browser)),
        Tool("scroll", "Scroll the page.", ScrollParams, ToolRiskLevel.LOW, _make_scroll(browser)),
        Tool("keypress", "Send a keyboard shortcut, e.g. 'cmd+t'.", KeypressParams, ToolRiskLevel.LOW, _make_keypress(browser, gate)),
        Tool("wait", "Pause for a short duration.", WaitParams, ToolRiskLevel.LOW, wait),
        Tool("ask_for_help", ASK_FOR_HELP_DESCRIPTION, AskForHelpParams, ToolRiskLevel.LOW, make_ask_for_help(help_request)),
        Tool("finish", "Report the subtask as complete with a result.", FinishParams, ToolRiskLevel.LOW, finish),
    ):
        registry.register(tool)
    return registry
