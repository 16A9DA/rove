from __future__ import annotations

import time

import Quartz
from AppKit import NSApplicationActivateIgnoringOtherApps, NSWorkspace

FOCUS_TIMEOUT_SECONDS = 1.0
FOCUS_POLL_INTERVAL_SECONDS = 0.05

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

    def screenshot(self) -> bytes:
        # CGWindowListCreateImage is deprecated on macOS 14+ but still works; swap for
        # ScreenCaptureKit if/when Apple removes it.
        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectInfinite, Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault
        )
        if image is None:
            raise RuntimeError("screenshot failed — check Screen Recording permission")

        from AppKit import NSBitmapImageRep, NSPNGFileType

        rep = NSBitmapImageRep.alloc().initWithCGImage_(image)
        data = rep.representationUsingType_properties_(NSPNGFileType, None)
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
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                # activateWithOptions_ is async — without this, click/type/keypress can
                # fire before macOS actually switches focus and hit the wrong window.
                deadline = time.monotonic() + FOCUS_TIMEOUT_SECONDS
                while time.monotonic() < deadline and self.get_active_application() != name:
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

    def list_windows(self) -> list[dict]:
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID
        )
        return [
            {"owner": w.get("kCGWindowOwnerName"), "title": w.get("kCGWindowName", ""), "bounds": w.get("kCGWindowBounds")}
            for w in windows
        ]
