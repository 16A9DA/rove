from __future__ import annotations

import os
import secrets
from pathlib import Path

TOKEN_PATH = Path(__file__).resolve().parent.parent / ".rove_token"


# A local-only shared secret. Without it any web page the user visits could call
# http://127.0.0.1:8000 and drive their computer (CORS only limits who can *read* replies).
# Persisted 0600 so the Electron shell (and a restarted backend) keep using the same one.
def load_token() -> str:
    env = os.environ.get("ROVE_API_TOKEN")
    if env:
        return env
    if TOKEN_PATH.exists():
        existing = TOKEN_PATH.read_text().strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(32)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    return token
