from __future__ import annotations

import re
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod

MAX_SPOKEN_CHARS = 400


class TTSError(Exception):
    pass


class TextToSpeechProvider(ABC):
    @abstractmethod
    def speak(self, text: str) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


# Spoken text should be short and free of markup/URLs read out character by character.
def clean_for_speech(text: str) -> str:
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"[`*_#>\[\]]", "", text)
    text = " ".join(text.split())
    if len(text) <= MAX_SPOKEN_CHARS:
        return text
    cut = text[:MAX_SPOKEN_CHARS]
    last_stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: last_stop + 1] if last_stop > 100 else cut.rstrip() + "…"


class MacSayTTS(TextToSpeechProvider):
    # macOS's built-in `say`: offline, no extra dependency. The text goes in over stdin as data
    # (never as an argument), so text starting with "-" can't become a flag and there is no shell.
    def __init__(self, voice: str | None = None) -> None:
        self._voice = voice
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        cleaned = clean_for_speech(text)
        if not cleaned:
            return
        binary = shutil.which("say")
        if binary is None:
            raise TTSError("the macOS `say` command is not available")
        self.stop()
        command = [binary] + (["-v", self._voice] if self._voice else [])
        with self._lock:
            self._proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            proc = self._proc
        try:
            assert proc.stdin is not None
            proc.stdin.write(cleaned)
            proc.stdin.close()
        except OSError:
            pass  # speech was stopped while we were writing

    def stop(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
