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
