from app.controllers import ComputerController


class FakeBrowserController(ComputerController):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.launched = False
        self.url: str | None = None

    @property
    def is_launched(self) -> bool:
        return self.launched

    @property
    def current_url(self) -> str | None:
        return self.url

    def launch(self) -> None:
        self.launched = True

    def navigate(self, url: str) -> None:
        self.url = url
        self.calls.append(("navigate", (url,)))

    def screenshot(self) -> bytes:
        return b"fake-browser-png"

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", (x, y)))

    def type(self, text: str) -> None:
        self.calls.append(("type", (text,)))

    def scroll(self, direction: str, amount: int = 3) -> None:
        self.calls.append(("scroll", (direction, amount)))

    def keypress(self, keys: str) -> None:
        self.calls.append(("keypress", (keys,)))

    def open_application(self, name: str) -> None:
        raise NotImplementedError("FakeBrowserController cannot open native applications")

    def focus_application(self, name: str) -> None:
        raise NotImplementedError("FakeBrowserController cannot focus native applications")

    def get_active_application(self) -> str | None:
        return "Chrome" if self.launched else None

    def get_text(self) -> str:
        return "fake browser page text"


class FakeNativeController(ComputerController):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.active_app: str | None = None

    def screenshot(self) -> bytes:
        return b"fake-native-png"

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", (x, y)))

    def type(self, text: str) -> None:
        self.calls.append(("type", (text,)))

    def scroll(self, direction: str, amount: int = 3) -> None:
        self.calls.append(("scroll", (direction, amount)))

    def keypress(self, keys: str) -> None:
        self.calls.append(("keypress", (keys,)))

    def open_application(self, name: str) -> None:
        self.active_app = name
        self.calls.append(("open_application", (name,)))

    def focus_application(self, name: str) -> None:
        self.active_app = name
        self.calls.append(("focus_application", (name,)))

    def get_active_application(self) -> str | None:
        return self.active_app

    def get_text(self) -> str:
        raise NotImplementedError("FakeNativeController cannot extract window text")
