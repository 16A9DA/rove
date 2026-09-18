from unittest.mock import MagicMock

import pytest

import app.native_controller as native_controller
from app.native_controller import NativeComputerController

# These tests mock every Quartz/AppKit call — real ones drive the live mouse/keyboard/
# screen, which isn't safe to fire off in an automated run. See the phase 7 test plan
# in the chat for the manual Finder/TextEdit checks that exercise the real APIs.


@pytest.fixture
def controller():
    return NativeComputerController()


def test_click_posts_move_down_up_in_order(controller, monkeypatch) -> None:
    create = MagicMock(return_value="event")
    post = MagicMock()
    monkeypatch.setattr(native_controller.Quartz, "CGEventCreateMouseEvent", create)
    monkeypatch.setattr(native_controller.Quartz, "CGEventPost", post)

    controller.click(10, 20)

    event_types = [call.args[1] for call in create.call_args_list]
    assert event_types == [
        native_controller.Quartz.kCGEventMouseMoved,
        native_controller.Quartz.kCGEventLeftMouseDown,
        native_controller.Quartz.kCGEventLeftMouseUp,
    ]
    assert post.call_count == 3


def test_type_posts_keydown_and_keyup_per_character(controller, monkeypatch) -> None:
    create = MagicMock(return_value="event")
    set_flags = MagicMock()
    post = MagicMock()
    monkeypatch.setattr(native_controller.Quartz, "CGEventCreateKeyboardEvent", create)
    monkeypatch.setattr(native_controller.Quartz, "CGEventSetFlags", set_flags)
    monkeypatch.setattr(native_controller.Quartz, "CGEventPost", post)

    controller.type("ab")

    assert create.call_count == 4  # keydown + keyup per character
    assert [call.args[1] for call in create.call_args_list] == [
        native_controller._KEY_CODES["a"], native_controller._KEY_CODES["a"],
        native_controller._KEY_CODES["b"], native_controller._KEY_CODES["b"],
    ]
    assert post.call_count == 4


def test_type_applies_shift_for_uppercase_and_symbols(controller, monkeypatch) -> None:
    create = MagicMock(return_value="event")
    set_flags = MagicMock()
    monkeypatch.setattr(native_controller.Quartz, "CGEventCreateKeyboardEvent", create)
    monkeypatch.setattr(native_controller.Quartz, "CGEventSetFlags", set_flags)
    monkeypatch.setattr(native_controller.Quartz, "CGEventPost", MagicMock())

    controller.type("A!")

    assert [call.args[1] for call in create.call_args_list] == [
        native_controller._KEY_CODES["a"], native_controller._KEY_CODES["a"],
        native_controller._KEY_CODES["1"], native_controller._KEY_CODES["1"],
    ]
    assert all(call.args[1] == native_controller._MODIFIER_FLAGS["shift"] for call in set_flags.call_args_list)


def test_type_unsupported_character_raises(controller) -> None:
    with pytest.raises(ValueError, match="unsupported character"):
        controller.type("€")


def test_scroll_converts_direction_to_wheel_deltas(controller, monkeypatch) -> None:
    create = MagicMock(return_value="event")
    monkeypatch.setattr(native_controller.Quartz, "CGEventCreateScrollWheelEvent", create)
    monkeypatch.setattr(native_controller.Quartz, "CGEventPost", MagicMock())

    controller.scroll("down", amount=2)

    _, _, _, dy, dx = create.call_args.args
    assert (dy, dx) == (-2, 0)


def test_keypress_applies_modifier_flags(controller, monkeypatch) -> None:
    create = MagicMock(return_value="event")
    set_flags = MagicMock()
    monkeypatch.setattr(native_controller.Quartz, "CGEventCreateKeyboardEvent", create)
    monkeypatch.setattr(native_controller.Quartz, "CGEventSetFlags", set_flags)
    monkeypatch.setattr(native_controller.Quartz, "CGEventPost", MagicMock())

    controller.keypress("cmd+t")

    assert [call.args[1] for call in create.call_args_list] == [native_controller._KEY_CODES["t"]] * 2
    assert set_flags.call_args_list[0].args[1] == native_controller._MODIFIER_FLAGS["cmd"]


def test_keypress_unknown_key_raises(controller) -> None:
    with pytest.raises(KeyError):
        controller.keypress("cmd+nonexistentkey")


def test_screenshot_raises_without_permission(controller, monkeypatch) -> None:
    monkeypatch.setattr(native_controller.Quartz, "CGWindowListCreateImage", MagicMock(return_value=None))

    with pytest.raises(RuntimeError, match="Screen Recording"):
        controller.screenshot()


def _fake_workspace(monkeypatch, workspace) -> None:
    # patch the module-level name native_controller imported, not the real ObjC
    # class — pyobjc class attributes don't support monkeypatch's undo via delattr.
    monkeypatch.setattr(native_controller, "NSWorkspace", MagicMock(sharedWorkspace=MagicMock(return_value=workspace)))


def test_get_active_application_returns_frontmost_app_name(controller, monkeypatch) -> None:
    workspace = MagicMock()
    workspace.frontmostApplication.return_value.localizedName.return_value = "TextEdit"
    _fake_workspace(monkeypatch, workspace)

    assert controller.get_active_application() == "TextEdit"


def test_get_active_application_returns_none_when_unknown(controller, monkeypatch) -> None:
    workspace = MagicMock()
    workspace.frontmostApplication.return_value = None
    _fake_workspace(monkeypatch, workspace)

    assert controller.get_active_application() is None


def test_focus_application_activates_matching_running_app(controller, monkeypatch) -> None:
    other = MagicMock()
    other.localizedName.return_value = "Finder"
    target = MagicMock()
    target.localizedName.return_value = "TextEdit"
    workspace = MagicMock()
    workspace.runningApplications.return_value = [other, target]
    # activation "succeeds" instantly: frontmostApplication already reports TextEdit
    workspace.frontmostApplication.return_value.localizedName.return_value = "TextEdit"
    _fake_workspace(monkeypatch, workspace)

    controller.focus_application("TextEdit")

    target.activateWithOptions_.assert_called_once()
    other.activateWithOptions_.assert_not_called()


def test_focus_application_waits_for_activation_to_land(controller, monkeypatch) -> None:
    target = MagicMock()
    target.localizedName.return_value = "TextEdit"
    workspace = MagicMock()
    workspace.runningApplications.return_value = [target]
    # frontmost app reports the old app for the first two polls, then the target — and
    # stays "landed" after that, since focus_application checks once more after the loop
    poll_count = {"n": 0}

    def fake_frontmost_name() -> str:
        poll_count["n"] += 1
        return "TextEdit" if poll_count["n"] >= 3 else "Terminal"

    workspace.frontmostApplication.return_value.localizedName.side_effect = fake_frontmost_name
    _fake_workspace(monkeypatch, workspace)
    monkeypatch.setattr(native_controller.time, "sleep", MagicMock())

    controller.focus_application("TextEdit")  # must not raise


def test_focus_application_raises_if_activation_never_lands(controller, monkeypatch) -> None:
    target = MagicMock()
    target.localizedName.return_value = "TextEdit"
    workspace = MagicMock()
    workspace.runningApplications.return_value = [target]
    workspace.frontmostApplication.return_value.localizedName.return_value = "Terminal"
    _fake_workspace(monkeypatch, workspace)
    monkeypatch.setattr(native_controller.time, "sleep", MagicMock())
    # fake clock jumps straight past the deadline so the test doesn't burn a real second
    clock = iter([0, 0, native_controller.FOCUS_TIMEOUT_SECONDS + 1])
    monkeypatch.setattr(native_controller.time, "monotonic", lambda: next(clock))

    with pytest.raises(RuntimeError, match="did not become frontmost"):
        controller.focus_application("TextEdit")


def test_focus_application_raises_when_not_running(controller, monkeypatch) -> None:
    workspace = MagicMock()
    workspace.runningApplications.return_value = []
    _fake_workspace(monkeypatch, workspace)

    with pytest.raises(RuntimeError, match="not running"):
        controller.focus_application("TextEdit")


def test_open_application_raises_on_failure(controller, monkeypatch) -> None:
    workspace = MagicMock()
    workspace.launchApplication_.return_value = False
    _fake_workspace(monkeypatch, workspace)

    with pytest.raises(RuntimeError, match="could not open"):
        controller.open_application("NoSuchApp")


def test_open_application_waits_for_process_to_register(controller, monkeypatch) -> None:
    target = MagicMock()
    target.localizedName.return_value = "TextEdit"
    workspace = MagicMock()
    workspace.launchApplication_.return_value = True
    # not running for the first poll, then registered
    workspace.runningApplications.side_effect = [[], [target]]
    _fake_workspace(monkeypatch, workspace)
    monkeypatch.setattr(native_controller.time, "sleep", MagicMock())

    controller.open_application("TextEdit")  # must not raise


def test_list_windows_maps_fields(controller, monkeypatch) -> None:
    monkeypatch.setattr(
        native_controller.Quartz,
        "CGWindowListCopyWindowInfo",
        MagicMock(return_value=[{"kCGWindowOwnerName": "Finder", "kCGWindowName": "Downloads", "kCGWindowBounds": {"X": 0}}]),
    )

    assert controller.list_windows() == [{"owner": "Finder", "title": "Downloads", "bounds": {"X": 0}}]
