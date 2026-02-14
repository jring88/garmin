from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import create_tables

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Garmin Health Dashboard", lifespan=lifespan)

# Import and include routers
from app.routers import journal, metrics, sync  # noqa: E402

app.include_router(sync.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(journal.router, prefix="/api")

# Serve static files (must be last so it doesn't shadow API routes)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
