from __future__ import annotations

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from app.controllers import ComputerController

# direction -> (dx, dy) unit vector; multiplied by amount * PIXELS_PER_UNIT for mouse.wheel
_SCROLL_VECTORS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_PIXELS_PER_UNIT = 100

# tool-layer keypress strings look like "cmd+t"; Playwright expects "Meta+T"
_MODIFIER_ALIASES = {"cmd": "Meta", "command": "Meta", "ctrl": "Control", "control": "Control", "alt": "Alt", "option": "Alt", "shift": "Shift"}


def _to_playwright_key(keys: str) -> str:
    parts = keys.split("+")
    *modifiers, key = parts
    mapped_modifiers = [_MODIFIER_ALIASES.get(m.lower(), m) for m in modifiers]
    mapped_key = key if len(key) > 1 else key.upper()
    return "+".join([*mapped_modifiers, mapped_key])


class BrowserController(ComputerController):
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def launch(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._page = self._browser.new_page()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = self._browser = self._page = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserController.launch() must be called first")
        return self._page

    def navigate(self, url: str) -> None:
        self.page.goto(url)

    @property
    def current_url(self) -> str:
        return self.page.url

    @property
    def page_title(self) -> str:
        return self.page.title()

    def wait(self, seconds: float) -> None:
        self.page.wait_for_timeout(seconds * 1000)

    def screenshot(self) -> bytes:
        return self.page.screenshot()

    def click(self, x: int, y: int) -> None:
        self.page.mouse.click(x, y)

    def type(self, text: str) -> None:
        self.page.keyboard.type(text)

    def scroll(self, direction: str, amount: int = 3) -> None:
        dx, dy = _SCROLL_VECTORS[direction]
        self.page.mouse.wheel(dx * amount * _PIXELS_PER_UNIT, dy * amount * _PIXELS_PER_UNIT)

    def keypress(self, keys: str) -> None:
        self.page.keyboard.press(_to_playwright_key(keys))

    def open_application(self, name: str) -> None:
        # a browser tab is not an OS application; use NativeComputerController (phase 7) for that
        raise NotImplementedError("BrowserController cannot open native applications")

    def focus_application(self, name: str) -> None:
        raise NotImplementedError("BrowserController cannot focus native applications")

    def get_active_application(self) -> str | None:
        return "Chrome" if self._page is not None else None
