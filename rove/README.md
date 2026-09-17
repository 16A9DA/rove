# Rove

## Overview

Rove is a macOS AI computer use assistant. It operates browsers and native applications on the user's behalf, driven by a goal given via text or voice.

## Structure

* `frontend/` — Next.js, TypeScript, Tailwind CSS
* `backend/` — FastAPI, Pydantic

## Install

```
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd frontend && npm install
```

Copy `.env.example` to `.env` and set `GROQ_API_KEY`.

## Usage

Backend:

```
cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app
```

Frontend:

```
cd frontend && npm run dev
```
