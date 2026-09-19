import numpy as np
import pytest

from app.stt import SAMPLE_RATE, MoonshineSTT, STTError


class FakeStream:
    def __init__(self, callback, seconds: float) -> None:
        self._callback = callback
        self._seconds = seconds

    def start(self) -> None:
        frames = int(SAMPLE_RATE * self._seconds)
        self._callback(np.zeros((frames, 1), dtype="float32"), None, None, None)

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakeMoonshine:
    def transcribe(self, audio, model=None):
        return ["hello world"]


def _patch_stream(monkeypatch, seconds: float) -> None:
    monkeypatch.setattr("sounddevice.InputStream", lambda **kw: FakeStream(kw["callback"], seconds))


def test_stop_before_start_raises() -> None:
    stt = MoonshineSTT()
    with pytest.raises(STTError):
        stt.stop_recording()


def test_double_start_raises(monkeypatch) -> None:
    _patch_stream(monkeypatch, seconds=1.0)
    stt = MoonshineSTT()
    stt.start_recording()

    with pytest.raises(STTError):
        stt.start_recording()


def test_start_stop_transcribes_buffered_audio(monkeypatch) -> None:
    _patch_stream(monkeypatch, seconds=1.0)
    stt = MoonshineSTT()
    monkeypatch.setattr(stt, "_ensure_model", lambda: (FakeMoonshine(), object()))

    stt.start_recording()
    transcript = stt.stop_recording()

    assert transcript == "hello world"


def test_stop_returns_empty_for_too_short_audio(monkeypatch) -> None:
    _patch_stream(monkeypatch, seconds=0.01)
    stt = MoonshineSTT()

    def fail_if_called():
        raise AssertionError("should not load the model for near-silent/too-short audio")

    monkeypatch.setattr(stt, "_ensure_model", fail_if_called)
    stt.start_recording()

    assert stt.stop_recording() == ""


def test_microphone_open_failure_raises_stt_error(monkeypatch) -> None:
    def _boom(**kwargs):
        raise OSError("no input device")

    monkeypatch.setattr("sounddevice.InputStream", _boom)
    stt = MoonshineSTT()

    with pytest.raises(STTError):
        stt.start_recording()
