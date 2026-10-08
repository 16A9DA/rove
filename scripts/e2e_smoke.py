"""End-to-end smoke check against a running backend.

    cd backend && PYTHONPATH=.. .venv/bin/uvicorn app.main:app      # in one terminal
    backend/.venv/bin/python scripts/e2e_smoke.py                    # API surface only, no model calls
    backend/.venv/bin/python scripts/e2e_smoke.py --live "Open Finder"   # also runs one real agent task (spends API tokens)
"""

import sys
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
TOKEN = (Path(__file__).resolve().parent.parent / "backend" / ".rove_token").read_text().strip()
AUTH = {"X-Rove-Token": TOKEN}
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=300)
    check("health is open", client.get("/health").status_code == 200)
    check("api rejects a missing token", client.get("/api/tasks").status_code == 401)
    check("api rejects a wrong token", client.get("/api/tasks", headers={"X-Rove-Token": "nope"}).status_code == 401)
    check("api accepts the token", client.get("/api/tasks", headers=AUTH).status_code == 200)

    settings = client.get("/api/settings", headers=AUTH)
    check("settings never echo raw keys", settings.status_code == 200 and not any("api_key" in k and isinstance(v, str) for k, v in settings.json().items()))
    check("memories list", client.get("/api/memories", headers=AUTH).status_code == 200)
    check("tts stop", client.post("/api/tts/stop", headers=AUTH).status_code == 200)
    check("unknown task is 404", client.get(f"/api/tasks/{uuid.uuid4()}", headers=AUTH).status_code == 404)
    check("resume without a paused run is 404", client.post("/api/agent/resume", json={"task_id": str(uuid.uuid4())}, headers=AUTH).status_code == 404)

    if "--live" in sys.argv:
        goal = sys.argv[sys.argv.index("--live") + 1]
        task_id = str(uuid.uuid4())
        run = client.post("/api/agent/run", json={"goal": goal, "task_id": task_id}, headers=AUTH)
        check("live run returns", run.status_code == 200, run.text[:200])
        task = client.get(f"/api/tasks/{task_id}", headers=AUTH).json()
        check("run was persisted with steps", bool(task.get("steps")), str(task)[:200])
        print(f"      result: {run.json().get('final_message') or run.json().get('error')}")

    print(f"\n{failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
