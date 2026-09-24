import json

from app.help_request import HelpRequest
from app.tools import ToolExecutor, ToolRiskLevel, browser_registry
from tests.conftest import FakeBrowserController


def test_registry_lists_all_browser_tools() -> None:
    names = {tool.name for tool in browser_registry(FakeBrowserController(), HelpRequest()).list()}
    assert names == {"open_url", "get_text", "screenshot", "click", "type", "scroll", "keypress", "wait", "ask_for_help", "finish"}


def test_all_browser_tools_are_low_risk() -> None:
    assert all(tool.risk_level == ToolRiskLevel.LOW for tool in browser_registry(FakeBrowserController(), HelpRequest()).list())


def test_open_url_launches_and_navigates() -> None:
    browser = FakeBrowserController()
    result = ToolExecutor(browser_registry(browser, HelpRequest())).execute("id1", "open_url", json.dumps({"url": "https://example.com"}))

    assert not result.is_error
    assert browser.launched
    assert browser.url == "https://example.com"


def test_click_targets_browser() -> None:
    browser = FakeBrowserController()
    result = ToolExecutor(browser_registry(browser, HelpRequest())).execute("id1", "click", json.dumps({"x": 5, "y": 6}))

    assert not result.is_error
    assert ("click", (5, 6)) in browser.calls


def test_get_text_returns_browser_text() -> None:
    browser = FakeBrowserController()
    result = ToolExecutor(browser_registry(browser, HelpRequest())).execute("id1", "get_text", "{}")

    assert not result.is_error
    assert json.loads(result.content)["text"] == "fake browser page text"


def test_screenshot_strips_image_onto_toolresult_not_content() -> None:
    browser = FakeBrowserController()
    result = ToolExecutor(browser_registry(browser, HelpRequest())).execute("id1", "screenshot", "{}")

    assert not result.is_error
    assert result.image_base64 == "ZmFrZS1icm93c2VyLXBuZw=="  # b"fake-browser-png"
    assert "_image_base64" not in result.content
    assert json.loads(result.content) == {"screenshot": "captured"}
