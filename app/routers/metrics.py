from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.database import async_session
from app.models import Activity, BodyComposition, DailySummary, HeartRate, Sleep
from app.schemas import (
    ActivityOut,
    BodyCompositionOut,
    DailySummaryOut,
    DashboardOut,
    HeartRateOut,
    SleepOut,
)

router = APIRouter(tags=["metrics"])


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(
    days: int = Query(30, ge=1, le=365),
):
    start = date.today() - timedelta(days=days)

    async with async_session() as session:
        activities = (
            await session.execute(
                select(Activity)
                .where(Activity.start_time >= start)
                .order_by(Activity.start_time.desc())
            )
        ).scalars().all()

        sleep = (
            await session.execute(
                select(Sleep)
                .where(Sleep.calendar_date >= start)
                .order_by(Sleep.calendar_date)
            )
        ).scalars().all()

        daily = (
            await session.execute(
                select(DailySummary)
                .where(DailySummary.calendar_date >= start)
                .order_by(DailySummary.calendar_date)
            )
        ).scalars().all()

        hr = (
            await session.execute(
                select(HeartRate)
                .where(HeartRate.calendar_date >= start)
                .order_by(HeartRate.calendar_date)
            )
        ).scalars().all()

        body = (
            await session.execute(
                select(BodyComposition)
                .where(BodyComposition.calendar_date >= start)
                .order_by(BodyComposition.calendar_date)
            )
        ).scalars().all()

    return DashboardOut(
        activities=[ActivityOut.model_validate(a) for a in activities],
        sleep=[SleepOut.model_validate(s) for s in sleep],
        daily=[DailySummaryOut.model_validate(d) for d in daily],
        heart_rate=[HeartRateOut.model_validate(h) for h in hr],
        body=[BodyCompositionOut.model_validate(b) for b in body],
    )


@router.get("/activities", response_model=list[ActivityOut])
async def get_activities(
    start: date | None = None,
    end: date | None = None,
    type: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    query = select(Activity).order_by(Activity.start_time.desc())
    if start:
        query = query.where(Activity.start_time >= start)
    if end:
        query = query.where(Activity.start_time <= end)
    if type:
        query = query.where(Activity.activity_type == type)
    query = query.limit(limit).offset(offset)

    async with async_session() as session:
        result = await session.execute(query)
        return [ActivityOut.model_validate(a) for a in result.scalars().all()]


@router.get("/sleep", response_model=list[SleepOut])
async def get_sleep(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    query = select(Sleep).order_by(Sleep.calendar_date.desc())
    if start:
        query = query.where(Sleep.calendar_date >= start)
    if end:
        query = query.where(Sleep.calendar_date <= end)
    query = query.limit(limit)

    async with async_session() as session:
        result = await session.execute(query)
        return [SleepOut.model_validate(s) for s in result.scalars().all()]


@router.get("/daily", response_model=list[DailySummaryOut])
async def get_daily(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    query = select(DailySummary).order_by(DailySummary.calendar_date.desc())
    if start:
        query = query.where(DailySummary.calendar_date >= start)
    if end:
        query = query.where(DailySummary.calendar_date <= end)
    query = query.limit(limit)

    async with async_session() as session:
        result = await session.execute(query)
        return [DailySummaryOut.model_validate(d) for d in result.scalars().all()]


@router.get("/heart-rate", response_model=list[HeartRateOut])
async def get_heart_rate(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    query = select(HeartRate).order_by(HeartRate.calendar_date.desc())
    if start:
        query = query.where(HeartRate.calendar_date >= start)
    if end:
        query = query.where(HeartRate.calendar_date <= end)
    query = query.limit(limit)

    async with async_session() as session:
        result = await session.execute(query)
        return [HeartRateOut.model_validate(h) for h in result.scalars().all()]


@router.get("/body", response_model=list[BodyCompositionOut])
async def get_body(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    query = select(BodyComposition).order_by(BodyComposition.calendar_date.desc())
    if start:
        query = query.where(BodyComposition.calendar_date >= start)
    if end:
        query = query.where(BodyComposition.calendar_date <= end)
    query = query.limit(limit)

    async with async_session() as session:
        result = await session.execute(query)
        return [BodyCompositionOut.model_validate(b) for b in result.scalars().all()]
