from __future__ import annotations

import time

import ApplicationServices
import Quartz
from AppKit import NSApplicationActivateIgnoringOtherApps, NSWorkspace

FOCUS_TIMEOUT_SECONDS = 3.0
FOCUS_POLL_INTERVAL_SECONDS = 0.05
SCREENSHOT_JPEG_QUALITY = 0.7

# AXMenuBar/AXMenu/AXMenuItem/AXMenuBarItem subtrees are invisible until a menu is
# actually open (they report real titles but zero-sized, meaningless positions until
# then) — pure noise for a click/type target list, so they're pruned on sight.
_AX_SKIP_ROLES = {"AXMenuBar", "AXMenu", "AXMenuItem", "AXMenuBarItem"}
_AX_MAX_DEPTH = 8
_AX_MAX_ELEMENTS = 60


def _ax_attr(element: object, attribute: str) -> object | None:
    error, value = ApplicationServices.AXUIElementCopyAttributeValue(element, attribute, None)
    return value if error == 0 else None


def _ax_point(value: object | None) -> tuple[int, int] | None:
    if value is None:
        return None
    ok, point = ApplicationServices.AXValueGetValue(value, ApplicationServices.kAXValueCGPointType, None)
    return (round(point.x), round(point.y)) if ok else None


def _ax_size(value: object | None) -> tuple[int, int] | None:
    if value is None:
        return None
    ok, size = ApplicationServices.AXValueGetValue(value, ApplicationServices.kAXValueCGSizeType, None)
    return (round(size.width), round(size.height)) if ok else None


def _walk_ax_tree(element: object, elements: list[dict], depth: int = 0) -> None:
    if depth > _AX_MAX_DEPTH or len(elements) >= _AX_MAX_ELEMENTS:
        return

    role = _ax_attr(element, ApplicationServices.kAXRoleAttribute)
    if role in _AX_SKIP_ROLES:
        return

    size = _ax_size(_ax_attr(element, ApplicationServices.kAXSizeAttribute))
    position = _ax_point(_ax_attr(element, ApplicationServices.kAXPositionAttribute))
    label = (
        _ax_attr(element, ApplicationServices.kAXTitleAttribute)
        or _ax_attr(element, ApplicationServices.kAXValueAttribute)
        or _ax_attr(element, ApplicationServices.kAXDescriptionAttribute)
    )

    # AXGroup is a layout container, not a clickable target — skip it unless it carries
    # its own label; every other role (button/field/text/window/...) with real on-screen
    # size is worth surfacing even unlabeled (an icon-only button still has a position).
    if role and size and size[0] > 0 and size[1] > 0 and (label or role != "AXGroup"):
        elements.append(
            {
                "role": role,
                "label": str(label)[:80] if label else None,
                "x": position[0] if position else None,
                "y": position[1] if position else None,
                "width": size[0],
                "height": size[1],
                "focused": bool(_ax_attr(element, ApplicationServices.kAXFocusedAttribute)),
            }
        )

    for child in _ax_attr(element, ApplicationServices.kAXChildrenAttribute) or []:
        if len(elements) >= _AX_MAX_ELEMENTS:
            return
        _walk_ax_tree(child, elements, depth + 1)

from app.controllers.base import ComputerController

# Requires two macOS grants for the process running this (System Settings -> Privacy &
# Security): Accessibility, for click/type/keypress synthetic input events, and Screen
# Recording, for screenshot(). open_application/focus_application/get_active_application
# and list_windows() need neither.

_SCROLL_VECTORS = {"up": (0, 1), "down": (0, -1), "left": (1, 0), "right": (-1, 0)}

# Standard ANSI-US virtual keycodes (Carbon HIToolbox values). Used by both keypress()
# and type() — the CGEventKeyboardSetUnicodeString "unicode override" trick was tried
# for type() first but several apps (TextEdit included) silently drop the override and
# fall back to the raw keycode, so type() now drives real keycodes + shift like keypress().
_KEY_CODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06, "x": 0x07,
    "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17,
    "=": 0x18, "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "o": 0x1F,
    "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28,
    ";": 0x29, "\\": 0x2A, ",": 0x2B, "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
    "tab": 0x30, "space": 0x31, "delete": 0x33, "escape": 0x35, "enter": 0x24, "return": 0x24,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}

# US-layout shift+key -> base key, for type()'s shifted symbols.
_SHIFTED_SYMBOLS = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}


def _resolve_char(char: str) -> tuple[int, bool]:
    if char == "\n":
        return _KEY_CODES["return"], False
    if char == " ":
        return _KEY_CODES["space"], False
    if char in _KEY_CODES:
        return _KEY_CODES[char], False
    if char.isupper() and char.lower() in _KEY_CODES:
        return _KEY_CODES[char.lower()], True
    if char in _SHIFTED_SYMBOLS:
        return _KEY_CODES[_SHIFTED_SYMBOLS[char]], True
    raise ValueError(f"type(): unsupported character {char!r}")

_MODIFIER_FLAGS = {
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "command": Quartz.kCGEventFlagMaskCommand,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "shift": Quartz.kCGEventFlagMaskShift,
}


class NativeComputerController(ComputerController):
    def __init__(self) -> None:
        self._source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)

    @property
    def source_state_id(self) -> int:
        # Tags every synthetic event this controller posts, so a global key-watcher
        # (see app/keyboard_watcher.py) can tell Rove's own keystrokes apart from a
        # real physical keypress and only cancel on the latter.
        return Quartz.CGEventSourceGetSourceStateID(self._source)

    def screenshot(self) -> bytes:
        # CGWindowListCreateImage is deprecated on macOS 14+ but still works; swap for
        # ScreenCaptureKit if/when Apple removes it.
        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectInfinite, Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault
        )
        if image is None:
            raise RuntimeError("screenshot failed — check Screen Recording permission")

        from Foundation import NSMutableData

        # CGWindowListCreateImage captures at retina backing resolution (e.g. 2x), but
        # click()/scroll() operate in logical display points — sending the raw retina
        # image means the model's on-screen coordinate guesses are 2x too large, and at
        # ~7000 image tokens it alone can exceed a provider's per-minute token budget.
        # Redraw at the logical display size (matching click()'s coordinate space) and
        # encode as JPEG, which is ~5x smaller than PNG at this resolution.
        display = Quartz.CGMainDisplayID()
        width, height = Quartz.CGDisplayPixelsWide(display), Quartz.CGDisplayPixelsHigh(display)
        color_space = Quartz.CGColorSpaceCreateDeviceRGB()
        context = Quartz.CGBitmapContextCreate(None, width, height, 8, 0, color_space, Quartz.kCGImageAlphaNoneSkipLast)
        Quartz.CGContextSetInterpolationQuality(context, Quartz.kCGInterpolationHigh)
        Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), image)
        scaled = Quartz.CGBitmapContextCreateImage(context)

        data = NSMutableData.data()
        destination = Quartz.CGImageDestinationCreateWithData(data, "public.jpeg", 1, None)
        Quartz.CGImageDestinationAddImage(
            destination, scaled, {Quartz.kCGImageDestinationLossyCompressionQuality: SCREENSHOT_JPEG_QUALITY}
        )
        Quartz.CGImageDestinationFinalize(destination)
        return bytes(data)

    def click(self, x: int, y: int) -> None:
        point = (x, y)
        for event_type in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            event = Quartz.CGEventCreateMouseEvent(self._source, event_type, point, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def type(self, text: str) -> None:
        for char in text:
            keycode, shift = _resolve_char(char)
            flags = _MODIFIER_FLAGS["shift"] if shift else 0
            for key_down in (True, False):
                event = Quartz.CGEventCreateKeyboardEvent(self._source, keycode, key_down)
                Quartz.CGEventSetFlags(event, flags)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def scroll(self, direction: str, amount: int = 3) -> None:
        dx, dy = _SCROLL_VECTORS[direction]
        event = Quartz.CGEventCreateScrollWheelEvent(self._source, Quartz.kCGScrollEventUnitLine, 2, dy * amount, dx * amount)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def keypress(self, keys: str) -> None:
        *modifier_names, key_name = keys.split("+")
        flags = 0
        for modifier in modifier_names:
            flags |= _MODIFIER_FLAGS[modifier.lower()]
        keycode = _KEY_CODES[key_name.lower()]

        for key_down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(self._source, keycode, key_down)
            Quartz.CGEventSetFlags(event, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def open_application(self, name: str) -> None:
        if not NSWorkspace.sharedWorkspace().launchApplication_(name):
            raise RuntimeError(f"could not open application: {name}")
        # launchApplication_ returns once the launch is *requested*, not once the process
        # is actually ready — a cold-launched app's first synthetic keystrokes can land
        # nowhere even though keypress()/cmd+n already worked (window creation succeeds
        # before the app's input handling is fully warmed up). Poll until it's running.
        deadline = time.monotonic() + FOCUS_TIMEOUT_SECONDS
        while time.monotonic() < deadline and not any(
            app.localizedName() == name for app in NSWorkspace.sharedWorkspace().runningApplications()
        ):
            time.sleep(FOCUS_POLL_INTERVAL_SECONDS)

    def focus_application(self, name: str) -> None:
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.localizedName() == name:
                # activateWithOptions_ is async and can be dropped/deferred (e.g. an app
                # with no open windows) — re-issue it on every poll instead of once, so a
                # missed activation gets retried rather than just waiting out the deadline.
                deadline = time.monotonic() + FOCUS_TIMEOUT_SECONDS
                while True:
                    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                    if self.get_active_application() == name or time.monotonic() >= deadline:
                        break
                    time.sleep(FOCUS_POLL_INTERVAL_SECONDS)
                if self.get_active_application() != name:
                    raise RuntimeError(f"{name} did not become frontmost within {FOCUS_TIMEOUT_SECONDS}s")
                return
        raise RuntimeError(f"application not running: {name}")

    def get_active_application(self) -> str | None:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.localizedName() if app else None

    def get_text(self) -> str:
        raise NotImplementedError("NativeComputerController cannot extract window text")

    def describe_ui(self) -> list[dict]:
        # grounds click()/type() in real elements instead of a screenshot pixel guess —
        # cheap text, no vision tokens, and gives exact coordinates/focus state
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return []
        ax_app = ApplicationServices.AXUIElementCreateApplication(app.processIdentifier())
        elements: list[dict] = []
        _walk_ax_tree(ax_app, elements)
        return elements

    def list_windows(self) -> list[dict]:
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID
        )
        return [
            {"owner": w.get("kCGWindowOwnerName"), "title": w.get("kCGWindowName", ""), "bounds": w.get("kCGWindowBounds")}
            for w in windows
        ]
