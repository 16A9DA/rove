from __future__ import annotations

from abc import ABC, abstractmethod


class ComputerController(ABC):
    # Generic interface the agent operates through — it must never depend on
    # whether the target is a browser (phase 6) or a native app (phase 7).

    @abstractmethod
    def screenshot(self) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def type(self, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def scroll(self, direction: str, amount: int = 3) -> None:
        raise NotImplementedError

    @abstractmethod
    def keypress(self, keys: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def open_application(self, name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def focus_application(self, name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_active_application(self) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_text(self) -> str:
        # extract visible text so a non-vision model can "observe" without a screenshot
        raise NotImplementedError

    def get_clipboard(self) -> str:
        raise NotImplementedError("this controller has no clipboard")

    def set_clipboard(self, text: str) -> None:
        raise NotImplementedError("this controller has no clipboard")

    def list_windows(self) -> list[dict]:
        raise NotImplementedError("this controller cannot list windows")

    def element_at(self, x: int, y: int) -> str | None:
        # label of whatever is under (x, y), for the permission gate; None when unknown
        return None

    @abstractmethod
    def describe_ui(self) -> list[dict]:
        # list on-screen interactive elements (role/label/position/size) so click/type
        # targets a real element instead of a guessed pixel from a screenshot
        raise NotImplementedError
