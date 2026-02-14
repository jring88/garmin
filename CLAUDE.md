# CLAUDE.md

## Project Overview

Garmin Health Insights Dashboard — a local web app that syncs Garmin Connect data into SQLite and displays an interactive dashboard.

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 + aiosqlite (SQLite)
- **Garmin API**: garminconnect library
- **Frontend**: Vanilla HTML/JS + Chart.js + Pico CSS (CDN)
- **Config**: pydantic-settings + .env

## Running

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
# Open http://localhost:8000
```

## Structure

- `app/main.py` — FastAPI app entry point
- `app/config.py` — Settings via pydantic-settings
- `app/database.py` — SQLAlchemy engine + session
- `app/models.py` — ORM models (7 tables)
- `app/schemas.py` — Pydantic request/response models
- `app/garmin_sync.py` — Incremental Garmin data sync
- `app/routers/` — API route handlers (sync, metrics, journal)
- `static/` — Frontend (index.html, app.js, style.css)
- `data/garmin_health.db` — SQLite database (gitignored)

There is no test suite, linter, or build system configured.
