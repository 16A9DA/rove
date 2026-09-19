from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod

import numpy as np

SAMPLE_RATE = 16_000


class STTError(Exception):
    """Raised for microphone/permission/transcription failures."""


class SpeechToTextProvider(ABC):
    @abstractmethod
    def start_recording(self) -> None: ...

    @abstractmethod
    def stop_recording(self) -> str:
        """Stop recording and return the transcript."""


class MoonshineSTT(SpeechToTextProvider):
    """Push-to-talk STT: start_recording buffers mic audio, stop_recording
    hands the whole buffer to Moonshine in one call. Moonshine is a seq2seq
    model over a fixed segment (0.1-64s), not a streaming decoder, so there
    is no partial-transcript-while-talking — "near-realtime" here means fast
    turnaround after stop (tiny model, short clips), not live captions.
    """

    def __init__(self, model_name: str = "moonshine/tiny") -> None:
        self._model_name = model_name
        self._model = None
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()

    def _ensure_model(self):
        os.environ.setdefault("KERAS_BACKEND", "torch")
        import moonshine  # heavy import (torch+keras) — deferred until actually used

        if self._model is None:
            self._model = moonshine.load_model(self._model_name)
        return moonshine, self._model

    def start_recording(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            raise STTError("already recording")

        self._chunks = []

        def _callback(indata, frames, time_info, status) -> None:
            with self._lock:
                self._chunks.append(indata.copy())

        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=_callback)
            stream.start()
        except Exception as exc:
            raise STTError(f"could not open microphone (check mic permission): {exc}") from exc
        self._stream = stream

    def stop_recording(self) -> str:
        if self._stream is None:
            raise STTError("not recording")

        self._stream.stop()
        self._stream.close()
        self._stream = None

        with self._lock:
            chunks, self._chunks = self._chunks, []

        if not chunks:
            return ""

        audio = np.concatenate(chunks, axis=0).reshape(1, -1).astype(np.float32)
        if audio.shape[-1] / SAMPLE_RATE < 0.1:
            return ""  # too short for Moonshine's minimum segment length

        moonshine, model = self._ensure_model()
        try:
            result = moonshine.transcribe(audio, model=model)
        except Exception as exc:
            raise STTError(f"transcription failed: {exc}") from exc
        return result[0] if result else ""
