"""Persisted provider/model/API-key choice for Settings. Gitignored JSON file next to
the sqlite memory DB — not env vars, since these are meant to be editable from the UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "rove_settings.json"

DEFAULTS: dict[str, Any] = {
    "provider": "anthropic",
    "model": None,
    "anthropic_api_key": None,
    "openai_api_key": None,
    "speak_results": True,
}


class SettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self._path = path

    def get(self) -> dict[str, Any]:
        if not self._path.exists():
            return dict(DEFAULTS)
        return {**DEFAULTS, **json.loads(self._path.read_text())}

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        # Blank values mean "leave as-is" (e.g. an empty API key field left untouched
        # in the UI shouldn't erase a previously saved key).
        current = self.get()
        for key, value in patch.items():
            if value or isinstance(value, bool):
                current[key] = value
        self._path.write_text(json.dumps(current))
        os.chmod(self._path, 0o600)  # holds API keys
        return current
