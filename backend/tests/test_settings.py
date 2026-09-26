from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, get_settings_store
from app.settings_store import SettingsStore

client = TestClient(app)


def _override_store(tmp_path) -> SettingsStore:
    store = SettingsStore(path=tmp_path / "rove_settings.json")
    app.dependency_overrides[get_settings_store] = lambda: store
    return store


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_get_settings_defaults(tmp_path) -> None:
    _override_store(tmp_path)

    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body == {"provider": "anthropic", "model": None, "has_anthropic_key": False, "has_openai_key": False}


def test_update_settings_saves_key_and_keeps_it_on_blank_update(tmp_path) -> None:
    _override_store(tmp_path)

    first = client.put("/api/settings", json={"provider": "openai", "model": "gpt-4o", "openai_api_key": "sk-test"})
    assert first.json() == {"provider": "openai", "model": "gpt-4o", "has_anthropic_key": False, "has_openai_key": True}

    second = client.put("/api/settings", json={"provider": "openai", "model": "gpt-4o-mini"})
    assert second.json()["has_openai_key"] is True
    assert second.json()["model"] == "gpt-4o-mini"


def test_list_models_requires_saved_key(tmp_path) -> None:
    _override_store(tmp_path)

    response = client.get("/api/models?provider=openai")

    assert response.status_code == 400


def test_list_models_returns_filtered_list(tmp_path) -> None:
    _override_store(tmp_path)
    client.put("/api/settings", json={"provider": "openai", "openai_api_key": "sk-test"})

    with patch("app.main.list_openai_models", return_value=[{"id": "gpt-4o", "display_name": "gpt-4o"}]) as mocked:
        response = client.get("/api/models?provider=openai")

    mocked.assert_called_once_with("sk-test")
    assert response.status_code == 200
    assert response.json() == {"models": [{"id": "gpt-4o", "display_name": "gpt-4o"}]}
