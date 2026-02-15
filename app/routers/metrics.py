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
    days: int = Query(30, ge=0),
    start: date | None = None,
    end: date | None = None,
):
    # Custom date range takes precedence over days
    if start or end:
        date_start = start
        date_end = end
    elif days > 0:
        date_start = date.today() - timedelta(days=days)
        date_end = None
    else:
        # days == 0 means all time
        date_start = None
        date_end = None

    async with async_session() as session:
        act_q = select(Activity).order_by(Activity.start_time.desc())
        if date_start:
            act_q = act_q.where(Activity.start_time >= date_start)
        if date_end:
            act_q = act_q.where(Activity.start_time <= date_end)
        activities = (await session.execute(act_q)).scalars().all()

        sleep_q = select(Sleep).order_by(Sleep.calendar_date)
        if date_start:
            sleep_q = sleep_q.where(Sleep.calendar_date >= date_start)
        if date_end:
            sleep_q = sleep_q.where(Sleep.calendar_date <= date_end)
        sleep = (await session.execute(sleep_q)).scalars().all()

        daily_q = select(DailySummary).order_by(DailySummary.calendar_date)
        if date_start:
            daily_q = daily_q.where(DailySummary.calendar_date >= date_start)
        if date_end:
            daily_q = daily_q.where(DailySummary.calendar_date <= date_end)
        daily = (await session.execute(daily_q)).scalars().all()

        hr_q = select(HeartRate).order_by(HeartRate.calendar_date)
        if date_start:
            hr_q = hr_q.where(HeartRate.calendar_date >= date_start)
        if date_end:
            hr_q = hr_q.where(HeartRate.calendar_date <= date_end)
        hr = (await session.execute(hr_q)).scalars().all()

        body_q = select(BodyComposition).order_by(BodyComposition.calendar_date)
        if date_start:
            body_q = body_q.where(BodyComposition.calendar_date >= date_start)
        if date_end:
            body_q = body_q.where(BodyComposition.calendar_date <= date_end)
        body = (await session.execute(body_q)).scalars().all()

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
