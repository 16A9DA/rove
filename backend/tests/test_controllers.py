import pytest

from app.controllers import ComputerController


class FakeComputerController(ComputerController):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.active_app: str | None = None

    def screenshot(self) -> bytes:
        self.calls.append(("screenshot", ()))
        return b"fake-png-bytes"

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
        self.calls.append(("get_text", ()))
        return "fake page text"


def test_cannot_instantiate_abstract_controller() -> None:
    with pytest.raises(TypeError):
        ComputerController()  # type: ignore[abstract]


def test_fake_controller_satisfies_interface() -> None:
    controller = FakeComputerController()

    assert controller.screenshot() == b"fake-png-bytes"
    controller.click(10, 20)
    controller.type("hello")
    controller.scroll("down", 5)
    controller.keypress("cmd+t")
    controller.open_application("Finder")
    assert controller.get_active_application() == "Finder"
    controller.focus_application("TextEdit")
    assert controller.get_active_application() == "TextEdit"

    assert controller.calls == [
        ("screenshot", ()),
        ("click", (10, 20)),
        ("type", ("hello",)),
        ("scroll", ("down", 5)),
        ("keypress", ("cmd+t",)),
        ("open_application", ("Finder",)),
        ("focus_application", ("TextEdit",)),
    ]


def test_incomplete_subclass_cannot_instantiate() -> None:
    class IncompleteController(ComputerController):
        def screenshot(self) -> bytes:
            return b""

    with pytest.raises(TypeError):
        IncompleteController()  # type: ignore[abstract]
