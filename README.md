# Rove

## Overview

Rove is a macOS AI computer use assistant. It operates browsers and native applications on the user's behalf, driven by a goal given via text or voice.

## Structure

* `frontend/` — Next.js, TypeScript, Tailwind CSS
* `backend/` — FastAPI, Pydantic
* `desktop/` — Electron macOS shell (menu bar + window)

## Install

```
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd backend && .venv/bin/python -m playwright install chromium
cd frontend && npm install
```

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

## Usage

Backend:

```
cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app
```

Frontend:

```
cd frontend && npm run dev
```

Desktop shell:

```
cd desktop && npm install
cd frontend && npm run dev   # keep this running in one terminal
cd desktop && npm run dev    # loads http://localhost:3000 in the Electron window
```

For a production-like run (loads the static export instead of the dev server):

```
cd frontend && npm run build
cd desktop && npm start
```

The app lives in the menu bar. Closing the window hides it; use "Quit Rove" from the tray menu or Cmd+Q to exit.
