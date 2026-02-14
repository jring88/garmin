# CLAUDE.md

## Project Overview

Garmin Health Insights Dashboard — a local, single-user web app that syncs data from Garmin Connect into a SQLite database and displays an interactive dashboard with charts and tables. Not deployed to production; runs locally only.

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), aiosqlite
- **Garmin API**: `garminconnect` library (blocking calls wrapped with `asyncio.to_thread`)
- **Frontend**: Vanilla HTML/JS single-page app, Chart.js 4 (CDN), Pico CSS 2.0 (CDN)
- **Config**: pydantic-settings loading from `.env`
- **Database**: SQLite via aiosqlite (stored at `data/garmin_health.db`)
- **Package management**: `pyproject.toml` (PEP 621), no lock file

## Running

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
# Open http://localhost:8000
```

Requires a `.env` file in the project root with:
```
GARMIN_EMAIL=<your_email>
GARMIN_PASSWORD=<your_password>
```

The `DATABASE_URL` defaults to `sqlite+aiosqlite:///data/garmin_health.db` and can be overridden in `.env`.

## Project Structure

```
app/
├── __init__.py
├── main.py            # FastAPI app, lifespan, router registration, static mount
├── config.py          # pydantic-settings Settings class (loads .env)
├── database.py        # Async SQLAlchemy engine, session maker, Base class
├── models.py          # 7 ORM models (Activity, Sleep, DailySummary, HeartRate,
│                      #   BodyComposition, Journal, SyncLog)
├── schemas.py         # Pydantic request/response models
├── garmin_sync.py     # Incremental sync logic for all data types
└── routers/
    ├── __init__.py
    ├── sync.py        # POST /api/sync/all, POST /api/sync/{type}, GET /api/sync/status
    ├── metrics.py     # GET /api/dashboard, activities, sleep, daily, heart-rate, body
    └── journal.py     # CRUD: GET/POST /api/journal, PUT/DELETE /api/journal/{id}

static/
├── index.html         # SPA shell with 5 tabs (Overview, Activities, Sleep, Body, Journal)
├── app.js             # All frontend logic: chart rendering, sync polling, CRUD
└── style.css          # Dark theme, responsive layout, CSS variables

data/
└── garmin_health.db   # SQLite database (gitignored)
```

## Database Schema

7 tables with no foreign key relationships — data is correlated by date:

| Table | Primary Key | Description |
|---|---|---|
| `activities` | `activity_id` (from Garmin, not auto-increment) | Exercise/activity records |
| `sleep` | `calendar_date` | Nightly sleep data |
| `daily_summary` | `calendar_date` | Daily step/calorie/stress/battery totals |
| `heart_rate` | `calendar_date` | Daily resting/max/min HR |
| `body_composition` | `calendar_date` | Weight, BMI, body fat, muscle mass |
| `journal` | `id` (auto-increment) | User-created journal entries |
| `sync_log` | `data_type` | Tracks last sync date/status per data type |

All Garmin data tables store the full API response in a `raw_json` column (JSON type).

## API Endpoints

All API routes are prefixed with `/api`. Static files are mounted at `/` (must be registered last to avoid shadowing API routes).

### Sync (`/api/sync`)
- `POST /api/sync/all` — trigger full sync (background task)
- `POST /api/sync/{data_type}` — sync one type: `activities`, `sleep`, `daily`, `heart_rate`, `body`
- `GET /api/sync/status` — returns live sync progress (polled by frontend every 2s)

### Metrics (`/api`)
- `GET /api/dashboard?days=30` — aggregated data across all types
- `GET /api/activities?start=&end=&type=&limit=&offset=`
- `GET /api/sleep?start=&end=&limit=`
- `GET /api/daily?start=&end=&limit=`
- `GET /api/heart-rate?start=&end=&limit=`
- `GET /api/body?start=&end=&limit=`

### Journal (`/api/journal`)
- `GET /api/journal?limit=&offset=&category=`
- `POST /api/journal` — body: `JournalCreate`
- `PUT /api/journal/{id}` — body: `JournalUpdate` (partial updates via `exclude_unset`)
- `DELETE /api/journal/{id}`

## Key Architecture Patterns

- **Async throughout**: FastAPI + async SQLAlchemy sessions + aiosqlite. Blocking Garmin API calls are wrapped with `asyncio.to_thread()`.
- **Lifespan startup**: `create_tables()` runs on app startup to ensure schema exists.
- **Dependency injection**: `get_session()` async generator provides DB sessions to route handlers.
- **Background sync**: Sync operations run via FastAPI `BackgroundTasks`; a global `sync_status` dict tracks real-time progress for the polling endpoint.
- **Incremental sync**: `SyncLog` tracks `last_synced_date` per data type. Only new data since that date is fetched. Empty streak detection skips forward 30 days after 14 consecutive empty days.
- **Upsert pattern**: All sync functions use SQLite `insert().on_conflict_do_update()` for idempotent writes.
- **Rate limiting**: 1-second delay (`asyncio.sleep(1)`) between Garmin API calls.
- **Static files last**: The `StaticFiles` mount at `/` must be the last mount to avoid shadowing `/api` routes.

## Conventions

- **Python style**: snake_case functions/variables, PascalCase classes, no type-stub files
- **ORM models**: SQLAlchemy 2.0 `Mapped[]` annotations with explicit column types
- **Column naming**: Units in names where applicable (`duration_seconds`, `distance_meters`, `weight_kg`, `body_fat_pct`)
- **Route naming**: Kebab-case paths (`/api/heart-rate`, `/api/body`)
- **Schemas**: Pydantic models with `model_config = ConfigDict(from_attributes=True)` for ORM compatibility
- **Frontend**: No build step, no framework — vanilla JS with Chart.js for visualization
- **Error handling**: Sync errors are logged and stored in `SyncLog.error_message`; journal 404s return `HTTPException`

## Testing and Linting

There is no test suite, linter, or build system configured. No CI/CD pipeline exists.

## Sensitive Files

- `.env` — contains Garmin credentials; gitignored, never commit
- `data/garmin_health.db` — contains personal health data; gitignored
