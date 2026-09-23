from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from app.controllers.base import ComputerController

T = TypeVar("T")

# direction -> (dx, dy) unit vector; multiplied by amount * PIXELS_PER_UNIT for mouse.wheel
_SCROLL_VECTORS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_PIXELS_PER_UNIT = 100

# tool-layer keypress strings look like "cmd+t"; Playwright expects "Meta+T"
_MODIFIER_ALIASES = {"cmd": "Meta", "command": "Meta", "ctrl": "Control", "control": "Control", "alt": "Alt", "option": "Alt", "shift": "Shift"}
# Models say "Return"/"return" for the Enter key; Playwright only recognizes "Enter".
_KEY_ALIASES = {"return": "Enter", "esc": "Escape"}


def _to_playwright_key(keys: str) -> str:
    parts = keys.split("+")
    *modifiers, key = parts
    mapped_modifiers = [_MODIFIER_ALIASES.get(m.lower(), m) for m in modifiers]
    mapped_key = _KEY_ALIASES.get(key.lower()) or (key if len(key) > 1 else key.upper())
    return "+".join([*mapped_modifiers, mapped_key])


class BrowserController(ComputerController):
    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        # Playwright's sync API is greenlet-based and thread-affine: every call has to
        # land on the same OS thread the Playwright object was created on. FastAPI runs
        # each request's sync endpoint on whatever threadpool thread is free, so without
        # this, tool calls from different requests randomly hit "Cannot switch to a
        # different thread". Route every Playwright touch through one dedicated thread.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")

    def _run(self, fn: Callable[[], T]) -> T:
        return self._executor.submit(fn).result()

    def _launch_impl(self) -> None:
        self._playwright = sync_playwright().start()
        # channel="chrome" drives the user's real installed Chrome, not Playwright's
        # bundled Chromium — headed so a "open Chrome" task is actually visible.
        self._browser = self._playwright.chromium.launch(channel="chrome", headless=self._headless)
        self._page = self._browser.new_page()

    def launch(self) -> None:
        self._run(self._launch_impl)

    @property
    def is_launched(self) -> bool:
        return self._page is not None

    def close(self) -> None:
        def _do() -> None:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
            self._playwright = self._browser = self._page = None

        self._run(_do)

    @property
    def page(self) -> Page:
        # Raw (unsubmitted) launch here — `page` is read from inside lambdas that `_run`
        # already dispatched onto the dedicated thread, so calling the public `launch()`
        # (which submits again and blocks on the result) would deadlock the one worker
        # against itself.
        if self._page is None:
            self._launch_impl()
        assert self._page is not None
        return self._page

    def navigate(self, url: str) -> None:
        self._run(lambda: self.page.goto(url))

    @property
    def current_url(self) -> str:
        return self._run(lambda: self.page.url)

    @property
    def page_title(self) -> str:
        return self._run(lambda: self.page.title())

    def wait(self, seconds: float) -> None:
        self._run(lambda: self.page.wait_for_timeout(seconds * 1000))

    def screenshot(self) -> bytes:
        # jpeg over the png default — cuts payload/token cost with no coordinate-space
        # impact here (Playwright's viewport already matches its own mouse coordinates).
        return self._run(lambda: self.page.screenshot(type="jpeg", quality=70))

    def click(self, x: int, y: int) -> None:
        self._run(lambda: self.page.mouse.click(x, y))

    def type(self, text: str) -> None:
        self._run(lambda: self.page.keyboard.type(text))

    def scroll(self, direction: str, amount: int = 3) -> None:
        dx, dy = _SCROLL_VECTORS[direction]
        self._run(lambda: self.page.mouse.wheel(dx * amount * _PIXELS_PER_UNIT, dy * amount * _PIXELS_PER_UNIT))

    def keypress(self, keys: str) -> None:
        self._run(lambda: self.page.keyboard.press(_to_playwright_key(keys)))

    def open_application(self, name: str) -> None:
        # a browser tab is not an OS application; use NativeComputerController (phase 7) for that
        raise NotImplementedError("BrowserController cannot open native applications")

    def focus_application(self, name: str) -> None:
        raise NotImplementedError("BrowserController cannot focus native applications")

    def get_active_application(self) -> str | None:
        return "Chrome" if self._page is not None else None

    def get_text(self) -> str:
        # ponytail: flat length cap, not smart summarization — raise if a real task needs more
        return self._run(lambda: self.page.inner_text("body"))[:5000]
