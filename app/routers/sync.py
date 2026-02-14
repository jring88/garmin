from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from app.database import async_session
from app.garmin_sync import SYNC_FUNCTIONS, sync_all, sync_one, sync_status
from app.models import SyncLog
from app.schemas import SyncStatusOut

router = APIRouter(tags=["sync"])


@router.post("/sync/all")
async def trigger_sync_all(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all)
    return {"message": "Sync started for all data types"}


@router.post("/sync/{data_type}")
async def trigger_sync_type(data_type: str, background_tasks: BackgroundTasks):
    if data_type not in SYNC_FUNCTIONS:
        return {"error": f"Unknown data type: {data_type}. Valid: {list(SYNC_FUNCTIONS.keys())}"}
    background_tasks.add_task(sync_one, data_type)
    return {"message": f"Sync started for {data_type}"}


@router.get("/sync/status", response_model=list[SyncStatusOut])
async def get_sync_status():
    async with async_session() as session:
        result = await session.execute(select(SyncLog))
        logs = result.scalars().all()

    statuses = []
    for log in logs:
        live = sync_status.get(log.data_type, {})
        statuses.append(
            SyncStatusOut(
                data_type=log.data_type,
                last_synced_date=log.last_synced_date,
                last_sync_at=log.last_sync_at,
                status=live.get("status", log.status),
                error_message=log.error_message,
                progress=live.get("progress"),
            )
        )

    # Include data types that are syncing but not yet in the DB
    for dt, live in sync_status.items():
        if not any(s.data_type == dt for s in statuses):
            statuses.append(
                SyncStatusOut(
                    data_type=dt,
                    status=live.get("status", "unknown"),
                    progress=live.get("progress"),
                )
            )

    return statuses
