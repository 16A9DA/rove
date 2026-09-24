import json

from app.help_request import HelpRequest
from app.tools import ToolExecutor, ToolRiskLevel, desktop_registry
from tests.conftest import FakeNativeController


def test_registry_lists_all_desktop_tools() -> None:
    names = {tool.name for tool in desktop_registry(FakeNativeController(), HelpRequest()).list()}
    assert names == {"open_application", "focus_application", "screenshot", "click", "type", "scroll", "keypress", "wait", "ask_for_help", "finish"}


def test_all_desktop_tools_are_low_risk() -> None:
    assert all(tool.risk_level == ToolRiskLevel.LOW for tool in desktop_registry(FakeNativeController(), HelpRequest()).list())


def test_open_application_activates_native() -> None:
    native = FakeNativeController()
    result = ToolExecutor(desktop_registry(native, HelpRequest())).execute("id1", "open_application", json.dumps({"name": "Finder"}))

    assert not result.is_error
    assert native.active_app == "Finder"


def test_screenshot_strips_image_onto_toolresult_not_content() -> None:
    native = FakeNativeController()
    result = ToolExecutor(desktop_registry(native, HelpRequest())).execute("id1", "screenshot", "{}")

    assert not result.is_error
    assert result.image_base64 == "ZmFrZS1uYXRpdmUtcG5n"  # b"fake-native-png"
    assert json.loads(result.content) == {"screenshot": "captured"}
