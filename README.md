# Rove

## Overview

Rove is a macOS AI computer use assistant. Give it a goal by text or voice. It plans the work and operates your browser, native apps and files for you, shows what it is doing, and asks before anything risky.

## Features

* Text and voice goals in the full app, plus a quick mode: hold Command, speak, release.
* Orchestrator with specialist agents for the browser, native apps, files and web research.
* Live activity feed and a live preview of the screen or page the agent is working on.
* Permission prompts for risky actions (sending, buying, deleting, overwriting).
* Pause and resume when you touch the mouse or keyboard, or when the agent needs your help. Stop at any time.
* Task history, saved across restarts, with step logs and a Yes/No rating on each result.
* Memory between tasks (preferences, past outcomes, learned workflows) that you can review and delete.
* Optional spoken results.
* Claude (Anthropic) or ChatGPT (OpenAI) as the model, chosen in Settings.

## Architecture

```
Electron shell (window, menu bar, popover)
        |
Next.js UI (static export)  <--- token header --->  FastAPI backend
                                                        |
                                              Orchestrator agent
                                   browser | desktop | files | research
                                                        |
                                  Permission gate, file sandbox, untrusted content wrapping
                                                        |
                                    Playwright (Chrome) | macOS controller (Quartz, AppKit)
```

Directories:

* `frontend/` Next.js, TypeScript, Tailwind. Built as a static export.
* `backend/` FastAPI, Pydantic. Providers, tools, controllers, persistence.
* `agents/` the tool calling loop and the orchestrator. Imported by the backend as a top level package.
* `desktop/` Electron macOS shell.
* `agentnet/` offline reference and evaluation data. Not part of the agent runtime.
* `scripts/` end to end smoke check.

## Requirements

* macOS
* Python 3 and Node.js
* Google Chrome installed (the browser agent drives your real Chrome)
* An Anthropic or OpenAI API key

## Install

```
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd backend && .venv/bin/python -m playwright install chromium
cd frontend && npm install
cd desktop && npm install
```

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`. You can also enter a key in Settings, which takes precedence.

The first install pulls in PyTorch through the speech model, so it is large.

## Run

Backend, from `backend/`:

```
PYTHONPATH=.. .venv/bin/uvicorn app.main:app --reload --reload-dir app --reload-dir ../agents
```

The desktop app starts this backend for you from `backend/.venv` if nothing is already answering on port 8000, logs to `~/Library/Logs/rove-desktop/backend.log`, and stops it when you quit. Because Electron launches it, macOS permissions attach to the Rove (Electron) app. Run it by hand as above when developing the backend.

On first start the backend creates `backend/.rove_token`. Every `/api` call must carry it in the `X-Rove-Token` header. The Electron shell reads it automatically.

Desktop app, development:

```
cd frontend && npm run dev     # keep running
cd desktop && npm run dev      # loads http://localhost:3000
```

Desktop app, production like:

```
cd frontend && npm run build
cd desktop && npm start        # loads frontend/out
```

To use the frontend in a plain browser during development, put the token in `frontend/.env.local`:

```
NEXT_PUBLIC_ROVE_TOKEN=<contents of backend/.rove_token>
```

## macOS permissions

Grant these to the app that launches the backend (Terminal, your editor or Electron):

* Accessibility and Input Monitoring: clicking, typing, the Command hold shortcut, pause on touch.
* Screen Recording: screenshots and the live preview.
* Microphone: voice input.

Without Input Monitoring the Command shortcut and pause on touch silently do nothing.

## Using Rove

* Type or speak a goal in the app. Rove shows each step as it happens.
* Hold Command alone for a moment, speak, then release. A small popover shows progress and the result. Holding Command again cuts off speech.
* Shortcuts: Command N new task, Command comma settings, Escape stops a running task.
* If a task pauses, use Continue, or Approve or Cancel when Rove asks permission.

## Safety model

* Rove never runs model written code or shell commands. The model only calls fixed tools with validated arguments.
* Clicks and keypresses are checked by what they would do (the control under the cursor, the form being submitted). Risky ones need your approval, and the model cannot approve for itself.
* File tools only reach Desktop, Documents and Downloads, never overwrite silently, and delete by moving to the Trash after approval. Change the folders with `ROVE_FILE_ROOTS`.
* Web pages, fetched pages and files are wrapped as untrusted data. Only your own request counts as an instruction.
* The backend API needs a local token, so other websites cannot drive your computer.
* API keys are stored in `backend/rove_settings.json` (owner only) and are never logged or returned by the API.

## Configuration

* `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`
* `ROVE_FILE_ROOTS` colon separated folders the file tools may use
* `ROVE_API_TOKEN` use a fixed token instead of `backend/.rove_token`
* `LANGSMITH_*` optional tracing, message content is never sent

## Development

```
cd backend && PYTHONPATH=.. .venv/bin/python -m pytest
cd backend && PYTHONPATH=.. .venv/bin/python -m pytest ../agentnet/tests
cd frontend && npm run lint
backend/.venv/bin/python scripts/e2e_smoke.py [--live "Open Finder"]
```

## Status and limitations

* Features added after the voice and orchestrator work (live activity, preview, permissions, files, recovery, injection defense, persistence, memory, spoken results, polish, API token) were built without running tests, lint, type checks or a live session. The smoke script exists but has not been run. Expect bugs and run it first.
* Task history and memory use SQLite, not PostgreSQL, because Rove is a single user local app.
* There is no packaged installer. Rove runs from the repository: the desktop app starts the backend from `backend/.venv`, so the install steps above are required. Bundling Python and PyTorch into a `.dmg` is not done.
* Clicks are still coordinate based. The permission check reads the control under the cursor but cannot see intent beyond that.
* Quick (Command hold) runs can pause for approval, but the popover cannot approve. Open the app.
