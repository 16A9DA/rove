from __future__ import annotations

from app.browser_controller import BrowserController
from app.controllers import ComputerController
from app.native_controller import NativeComputerController


class ComputerEnvironment:
    # Owns both controllers and tracks which is "active". open_url/open_application/
    # focus_application switch it; click/type/scroll/keypress/screenshot always target
    # whichever is currently active.
    def __init__(self, browser: BrowserController | None = None, native: ComputerController | None = None) -> None:
        self.browser = browser if browser is not None else BrowserController()
        self.native = native if native is not None else NativeComputerController()
        self.active: ComputerController = self.native

    def open_url(self, url: str) -> None:
        if not self.browser.is_launched:
            self.browser.launch()
        self.browser.navigate(url)
        self.active = self.browser

    def open_application(self, name: str) -> None:
        self.native.open_application(name)
        self.active = self.native

    def focus_application(self, name: str) -> None:
        self.native.focus_application(name)
        self.active = self.native
