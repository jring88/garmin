import asyncio
import json
import logging
from datetime import date, datetime, timedelta

from garminconnect import Garmin
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.database import async_session
from app.models import (
    Activity,
    BodyComposition,
    DailySummary,
    HeartRate,
    Sleep,
    SyncLog,
)

logger = logging.getLogger(__name__)

# Absolute fallback if we can't determine earliest activity date
FALLBACK_START = date(2015, 1, 1)

# Global sync state for status polling
sync_status: dict[str, dict] = {}


def get_garmin_client() -> Garmin:
    client = Garmin(settings.garmin_email, settings.garmin_password)
    client.login()
    return client


async def get_first_sync_start() -> date:
    """Determine a smart start date for first-time syncs by looking at the
    earliest activity already in the DB (activities sync via pagination so
    they always go all the way back).  Falls back to FALLBACK_START."""
    async with async_session() as session:
        result = await session.execute(
            select(Activity.start_time)
            .where(Activity.start_time.isnot(None))
            .order_by(Activity.start_time.asc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return row.date()
    return FALLBACK_START


async def get_last_synced_date(data_type: str) -> date | None:
    async with async_session() as session:
        result = await session.execute(
            select(SyncLog.last_synced_date).where(SyncLog.data_type == data_type)
        )
        row = result.scalar_one_or_none()
        return row


async def update_sync_log(
    data_type: str,
    last_date: date,
    status: str = "completed",
    error: str | None = None,
):
    async with async_session() as session:
        stmt = sqlite_insert(SyncLog).values(
            data_type=data_type,
            last_synced_date=last_date,
            last_sync_at=datetime.utcnow(),
            status=status,
            error_message=error,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["data_type"],
            set_={
                "last_synced_date": last_date,
                "last_sync_at": datetime.utcnow(),
                "status": status,
                "error_message": error,
            },
        )
        await session.execute(stmt)
        await session.commit()


async def sync_activities(client: Garmin):
    data_type = "activities"
    sync_status[data_type] = {"status": "syncing", "progress": "Fetching activities..."}

    try:
        last_date = await get_last_synced_date(data_type)
        start = 0
        batch_size = 100
        latest_date = last_date or date.min

        while True:
            sync_status[data_type]["progress"] = f"Fetching batch at offset {start}..."
            activities = await asyncio.to_thread(
                client.get_activities, start, batch_size
            )
            if not activities:
                break

            async with async_session() as session:
                for a in activities:
                    activity_date = None
                    if a.get("startTimeLocal"):
                        try:
                            activity_date = datetime.fromisoformat(
                                a["startTimeLocal"]
                            ).date()
                        except (ValueError, TypeError):
                            pass

                    # Skip if we've already synced past this date
                    if last_date and activity_date and activity_date <= last_date:
                        # We've reached already-synced data, stop
                        await session.commit()
                        if activity_date > latest_date:
                            latest_date = activity_date
                        # Since activities are returned newest-first, keep going
                        # until we've checked the whole batch
                        continue

                    if activity_date and activity_date > latest_date:
                        latest_date = activity_date

                    start_time = None
                    if a.get("startTimeLocal"):
                        try:
                            start_time = datetime.fromisoformat(a["startTimeLocal"])
                        except (ValueError, TypeError):
                            pass

                    stmt = sqlite_insert(Activity).values(
                        activity_id=a["activityId"],
                        activity_type=a.get("activityType", {}).get("typeKey"),
                        activity_name=a.get("activityName"),
                        start_time=start_time,
                        duration_seconds=a.get("duration"),
                        distance_meters=a.get("distance"),
                        avg_hr=a.get("averageHR"),
                        max_hr=a.get("maxHR"),
                        avg_speed=a.get("averageSpeed"),
                        max_speed=a.get("maxSpeed"),
                        calories=a.get("calories"),
                        cadence=a.get("averageRunningCadenceInStepsPerMinute")
                        or a.get("averageBikingCadenceInRevPerMinute"),
                        vo2max=a.get("vO2MaxValue"),
                        training_effect_aerobic=a.get("aerobicTrainingEffect"),
                        training_effect_anaerobic=a.get("anaerobicTrainingEffect"),
                        elevation_gain=a.get("elevationGain"),
                        raw_json=a,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["activity_id"],
                        set_={
                            "activity_type": a.get("activityType", {}).get("typeKey"),
                            "activity_name": a.get("activityName"),
                            "start_time": start_time,
                            "duration_seconds": a.get("duration"),
                            "distance_meters": a.get("distance"),
                            "avg_hr": a.get("averageHR"),
                            "max_hr": a.get("maxHR"),
                            "avg_speed": a.get("averageSpeed"),
                            "max_speed": a.get("maxSpeed"),
                            "calories": a.get("calories"),
                            "vo2max": a.get("vO2MaxValue"),
                            "training_effect_aerobic": a.get("aerobicTrainingEffect"),
                            "training_effect_anaerobic": a.get("anaerobicTrainingEffect"),
                            "elevation_gain": a.get("elevationGain"),
                            "raw_json": a,
                        },
                    )
                    await session.execute(stmt)
                await session.commit()

            # If fewer than batch_size returned, we've reached the end
            if len(activities) < batch_size:
                break

            start += batch_size
            await asyncio.sleep(1)  # Rate limit

        if latest_date > date.min:
            await update_sync_log(data_type, latest_date)
        sync_status[data_type] = {"status": "completed", "progress": "Done"}

    except Exception as e:
        logger.exception(f"Error syncing {data_type}")
        sync_status[data_type] = {"status": "error", "progress": str(e)}
        await update_sync_log(data_type, date.today(), "error", str(e))


async def sync_sleep(client: Garmin):
    data_type = "sleep"
    sync_status[data_type] = {"status": "syncing", "progress": "Fetching sleep data..."}

    try:
        last_date = await get_last_synced_date(data_type)
        start_date = (last_date + timedelta(days=1)) if last_date else await get_first_sync_start()
        end_date = date.today()
        current = start_date
        latest_date = last_date or date.min

        while current <= end_date:
            sync_status[data_type]["progress"] = f"Fetching sleep for {current}..."
            try:
                data = await asyncio.to_thread(
                    client.get_sleep_data, current.isoformat()
                )
            except Exception as e:
                logger.warning(f"Failed to fetch sleep for {current}: {e}")
                current += timedelta(days=1)
                await asyncio.sleep(1)
                continue

            if data and data.get("dailySleepDTO"):
                s = data["dailySleepDTO"]

                sleep_start = None
                sleep_end = None
                if s.get("sleepStartTimestampLocal"):
                    sleep_start = datetime.fromtimestamp(
                        s["sleepStartTimestampLocal"] / 1000
                    )
                if s.get("sleepEndTimestampLocal"):
                    sleep_end = datetime.fromtimestamp(
                        s["sleepEndTimestampLocal"] / 1000
                    )

                async with async_session() as session:
                    stmt = sqlite_insert(Sleep).values(
                        calendar_date=current,
                        sleep_start=sleep_start,
                        sleep_end=sleep_end,
                        total_sleep_seconds=s.get("sleepTimeSeconds"),
                        deep_seconds=s.get("deepSleepSeconds"),
                        light_seconds=s.get("lightSleepSeconds"),
                        rem_seconds=s.get("remSleepSeconds"),
                        awake_seconds=s.get("awakeSleepSeconds"),
                        sleep_score=data.get("sleepScores", {}).get("overall", {}).get("value")
                        if data.get("sleepScores")
                        else None,
                        avg_respiration=s.get("averageRespiration"),
                        avg_spo2=s.get("averageSpO2Value"),
                        avg_stress=None,
                        resting_hr=None,
                        raw_json=data,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["calendar_date"],
                        set_={
                            "sleep_start": sleep_start,
                            "sleep_end": sleep_end,
                            "total_sleep_seconds": s.get("sleepTimeSeconds"),
                            "deep_seconds": s.get("deepSleepSeconds"),
                            "light_seconds": s.get("lightSleepSeconds"),
                            "rem_seconds": s.get("remSleepSeconds"),
                            "awake_seconds": s.get("awakeSleepSeconds"),
                            "sleep_score": data.get("sleepScores", {}).get("overall", {}).get("value")
                            if data.get("sleepScores")
                            else None,
                            "avg_respiration": s.get("averageRespiration"),
                            "avg_spo2": s.get("averageSpO2Value"),
                            "raw_json": data,
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()

                if current > latest_date:
                    latest_date = current

            current += timedelta(days=1)
            await asyncio.sleep(1)

        if latest_date > date.min:
            await update_sync_log(data_type, latest_date)
        sync_status[data_type] = {"status": "completed", "progress": "Done"}

    except Exception as e:
        logger.exception(f"Error syncing {data_type}")
        sync_status[data_type] = {"status": "error", "progress": str(e)}
        await update_sync_log(data_type, date.today(), "error", str(e))


async def sync_daily_summary(client: Garmin):
    data_type = "daily"
    sync_status[data_type] = {"status": "syncing", "progress": "Fetching daily summaries..."}

    try:
        last_date = await get_last_synced_date(data_type)
        start_date = (last_date + timedelta(days=1)) if last_date else await get_first_sync_start()
        end_date = date.today()
        current = start_date
        latest_date = last_date or date.min

        while current <= end_date:
            sync_status[data_type]["progress"] = f"Fetching daily for {current}..."
            try:
                data = await asyncio.to_thread(
                    client.get_stats, current.isoformat()
                )
            except Exception as e:
                logger.warning(f"Failed to fetch daily for {current}: {e}")
                current += timedelta(days=1)
                await asyncio.sleep(1)
                continue

            has_data = data and (data.get("totalSteps") or data.get("restingHeartRate") or data.get("totalKilocalories"))

            if has_data:
                async with async_session() as session:
                    stmt = sqlite_insert(DailySummary).values(
                        calendar_date=current,
                        steps=data.get("totalSteps"),
                        total_distance_meters=data.get("totalDistanceMeters"),
                        active_calories=data.get("activeKilocalories"),
                        total_calories=data.get("totalKilocalories"),
                        resting_hr=data.get("restingHeartRate"),
                        max_hr=data.get("maxHeartRate"),
                        avg_stress=data.get("averageStressLevel"),
                        max_stress=data.get("maxStressLevel"),
                        body_battery_high=data.get("bodyBatteryChargedValue"),
                        body_battery_low=data.get("bodyBatteryDrainedValue"),
                        floors_climbed=data.get("floorsAscended"),
                        intensity_minutes=data.get("moderateIntensityMinutes", 0)
                        + data.get("vigorousIntensityMinutes", 0)
                        if data.get("moderateIntensityMinutes") is not None
                        else None,
                        raw_json=data,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["calendar_date"],
                        set_={
                            "steps": data.get("totalSteps"),
                            "total_distance_meters": data.get("totalDistanceMeters"),
                            "active_calories": data.get("activeKilocalories"),
                            "total_calories": data.get("totalKilocalories"),
                            "resting_hr": data.get("restingHeartRate"),
                            "max_hr": data.get("maxHeartRate"),
                            "avg_stress": data.get("averageStressLevel"),
                            "max_stress": data.get("maxStressLevel"),
                            "body_battery_high": data.get("bodyBatteryChargedValue"),
                            "body_battery_low": data.get("bodyBatteryDrainedValue"),
                            "floors_climbed": data.get("floorsAscended"),
                            "raw_json": data,
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()

                if current > latest_date:
                    latest_date = current

            current += timedelta(days=1)
            await asyncio.sleep(1)

        if latest_date > date.min:
            await update_sync_log(data_type, latest_date)
        sync_status[data_type] = {"status": "completed", "progress": "Done"}

    except Exception as e:
        logger.exception(f"Error syncing {data_type}")
        sync_status[data_type] = {"status": "error", "progress": str(e)}
        await update_sync_log(data_type, date.today(), "error", str(e))


async def sync_heart_rate(client: Garmin):
    data_type = "heart_rate"
    sync_status[data_type] = {"status": "syncing", "progress": "Fetching heart rate..."}

    try:
        last_date = await get_last_synced_date(data_type)
        start_date = (last_date + timedelta(days=1)) if last_date else await get_first_sync_start()
        end_date = date.today()
        current = start_date
        latest_date = last_date or date.min

        while current <= end_date:
            sync_status[data_type]["progress"] = f"Fetching HR for {current}..."
            try:
                data = await asyncio.to_thread(
                    client.get_heart_rates, current.isoformat()
                )
            except Exception as e:
                logger.warning(f"Failed to fetch HR for {current}: {e}")
                current += timedelta(days=1)
                await asyncio.sleep(1)
                continue

            has_data = data and (data.get("restingHeartRate") or data.get("maxHeartRate"))

            if has_data:
                async with async_session() as session:
                    stmt = sqlite_insert(HeartRate).values(
                        calendar_date=current,
                        resting_hr=data.get("restingHeartRate"),
                        max_hr=data.get("maxHeartRate"),
                        min_hr=data.get("minHeartRate"),
                        raw_json=data,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["calendar_date"],
                        set_={
                            "resting_hr": data.get("restingHeartRate"),
                            "max_hr": data.get("maxHeartRate"),
                            "min_hr": data.get("minHeartRate"),
                            "raw_json": data,
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()

                if current > latest_date:
                    latest_date = current

            current += timedelta(days=1)
            await asyncio.sleep(1)

        if latest_date > date.min:
            await update_sync_log(data_type, latest_date)
        sync_status[data_type] = {"status": "completed", "progress": "Done"}

    except Exception as e:
        logger.exception(f"Error syncing {data_type}")
        sync_status[data_type] = {"status": "error", "progress": str(e)}
        await update_sync_log(data_type, date.today(), "error", str(e))


async def sync_body_composition(client: Garmin):
    data_type = "body"
    sync_status[data_type] = {"status": "syncing", "progress": "Fetching body composition..."}

    try:
        last_date = await get_last_synced_date(data_type)
        start_date = (last_date + timedelta(days=1)) if last_date else await get_first_sync_start()
        end_date = date.today()

        sync_status[data_type]["progress"] = "Fetching weight data..."
        try:
            data = await asyncio.to_thread(
                client.get_body_composition,
                start_date.isoformat(),
                end_date.isoformat(),
            )
        except Exception as e:
            logger.warning(f"Failed to fetch body composition: {e}")
            sync_status[data_type] = {"status": "error", "progress": str(e)}
            await update_sync_log(data_type, date.today(), "error", str(e))
            return

        latest_date = last_date or date.min

        if data and data.get("dateWeightList"):
            async with async_session() as session:
                for entry in data["dateWeightList"]:
                    cal_date_ts = entry.get("calendarDate")
                    if not cal_date_ts:
                        continue
                    try:
                        cal_date = date.fromisoformat(cal_date_ts)
                    except (ValueError, TypeError):
                        continue

                    weight = entry.get("weight")
                    if weight:
                        weight = weight / 1000.0  # grams to kg

                    stmt = sqlite_insert(BodyComposition).values(
                        calendar_date=cal_date,
                        weight_kg=weight,
                        bmi=entry.get("bmi"),
                        body_fat_pct=entry.get("bodyFat"),
                        muscle_mass_kg=(entry.get("muscleMass") or 0) / 1000.0
                        if entry.get("muscleMass")
                        else None,
                        bone_mass_kg=(entry.get("boneMass") or 0) / 1000.0
                        if entry.get("boneMass")
                        else None,
                        body_water_pct=entry.get("bodyWater"),
                        raw_json=entry,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["calendar_date"],
                        set_={
                            "weight_kg": weight,
                            "bmi": entry.get("bmi"),
                            "body_fat_pct": entry.get("bodyFat"),
                            "muscle_mass_kg": (entry.get("muscleMass") or 0) / 1000.0
                            if entry.get("muscleMass")
                            else None,
                            "bone_mass_kg": (entry.get("boneMass") or 0) / 1000.0
                            if entry.get("boneMass")
                            else None,
                            "body_water_pct": entry.get("bodyWater"),
                            "raw_json": entry,
                        },
                    )
                    await session.execute(stmt)
                    if cal_date > latest_date:
                        latest_date = cal_date
                await session.commit()

        if latest_date > date.min:
            await update_sync_log(data_type, latest_date)
        sync_status[data_type] = {"status": "completed", "progress": "Done"}

    except Exception as e:
        logger.exception(f"Error syncing {data_type}")
        sync_status[data_type] = {"status": "error", "progress": str(e)}
        await update_sync_log(data_type, date.today(), "error", str(e))


SYNC_FUNCTIONS = {
    "activities": sync_activities,
    "sleep": sync_sleep,
    "daily": sync_daily_summary,
    "heart_rate": sync_heart_rate,
    "body": sync_body_composition,
}


async def sync_all():
    client = await asyncio.to_thread(get_garmin_client)
    for data_type, func in SYNC_FUNCTIONS.items():
        await func(client)


async def sync_one(data_type: str):
    if data_type not in SYNC_FUNCTIONS:
        raise ValueError(f"Unknown data type: {data_type}")
    client = await asyncio.to_thread(get_garmin_client)
    await SYNC_FUNCTIONS[data_type](client)
