from fastapi.testclient import TestClient

from app.main import app, get_stt_provider
from app.stt import STTError

client = TestClient(app)


class FakeSTT:
    def __init__(self, transcript: str = "", error: STTError | None = None) -> None:
        self._transcript = transcript
        self._error = error

    def start_recording(self) -> None:
        if self._error:
            raise self._error

    def stop_recording(self) -> str:
        if self._error:
            raise self._error
        return self._transcript


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_stt_start_and_stop_returns_transcript() -> None:
    app.dependency_overrides[get_stt_provider] = lambda: FakeSTT(transcript="open finder")

    start = client.post("/api/stt/start")
    stop = client.post("/api/stt/stop")

    assert start.status_code == 200
    assert stop.status_code == 200
    assert stop.json() == {"transcript": "open finder"}


def test_stt_start_surfaces_microphone_error() -> None:
    app.dependency_overrides[get_stt_provider] = lambda: FakeSTT(error=STTError("no mic permission"))

    response = client.post("/api/stt/start")

    assert response.status_code == 400
    assert response.json()["detail"] == "no mic permission"
