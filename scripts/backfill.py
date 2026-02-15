"""
One-time backfill script for Garmin health data.

Fetches sleep, daily summary, and heart rate data day-by-day from the
earliest activity date to today, then bulk-fetches body composition.
No skip logic — every day is fetched unconditionally.

Usage:
    source .venv/bin/activate
    python scripts/backfill.py
"""

import asyncio
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Ensure the project root is on sys.path so `app` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.database import async_session, create_tables
from app.garmin_sync import get_garmin_client, update_sync_log
from app.models import (
    BodyComposition,
    DailySummary,
    HeartRate,
    Sleep,
    Activity,
)

DELAY = 0.25  # seconds between API calls


async def get_earliest_activity_date() -> date:
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
    return date(2021, 2, 5)  # hardcoded fallback from plan


async def cleanup_tables():
    print("\nThis will DELETE all existing sleep, daily_summary, heart_rate,")
    print("body_composition data and their sync_log entries, then re-fetch everything.")
    answer = input("\nProceed? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    async with async_session() as session:
        await session.execute(text("DELETE FROM sync_log WHERE data_type IN ('sleep', 'daily', 'heart_rate', 'body')"))
        await session.execute(text("DELETE FROM sleep"))
        await session.execute(text("DELETE FROM daily_summary"))
        await session.execute(text("DELETE FROM heart_rate"))
        await session.execute(text("DELETE FROM body_composition"))
        await session.commit()
    print("Cleaned up existing data.\n")


async def backfill_day_based(client, start_date: date, end_date: date):
    """Fetch sleep, daily summary, and heart rate for every day in range."""
    current = start_date
    total_days = (end_date - start_date).days + 1
    sleep_count = 0
    daily_count = 0
    hr_count = 0

    while current <= end_date:
        day_str = current.isoformat()
        day_num = (current - start_date).days + 1
        sleep_ok = daily_ok = hr_ok = False

        # --- Sleep ---
        try:
            data = await asyncio.to_thread(client.get_sleep_data, day_str)
            if data and data.get("dailySleepDTO"):
                s = data["dailySleepDTO"]
                sleep_start = None
                sleep_end = None
                if s.get("sleepStartTimestampLocal"):
                    sleep_start = datetime.fromtimestamp(s["sleepStartTimestampLocal"] / 1000)
                if s.get("sleepEndTimestampLocal"):
                    sleep_end = datetime.fromtimestamp(s["sleepEndTimestampLocal"] / 1000)

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
                sleep_ok = True
                sleep_count += 1
        except Exception as e:
            print(f"  sleep error on {day_str}: {e}")
        await asyncio.sleep(DELAY)

        # --- Daily Summary ---
        try:
            data = await asyncio.to_thread(client.get_stats, day_str)
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
                daily_ok = True
                daily_count += 1
        except Exception as e:
            print(f"  daily error on {day_str}: {e}")
        await asyncio.sleep(DELAY)

        # --- Heart Rate ---
        try:
            data = await asyncio.to_thread(client.get_heart_rates, day_str)
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
                hr_ok = True
                hr_count += 1
        except Exception as e:
            print(f"  hr error on {day_str}: {e}")
        await asyncio.sleep(DELAY)

        marks = f"sleep {'✓' if sleep_ok else '·'} daily {'✓' if daily_ok else '·'} hr {'✓' if hr_ok else '·'}"
        print(f"[{day_num}/{total_days}] {day_str} — {marks}")

        current += timedelta(days=1)

    return sleep_count, daily_count, hr_count


async def backfill_body_composition(client, start_date: date, end_date: date):
    """Bulk-fetch body composition using the date-range API."""
    print("\nFetching body composition...")
    try:
        data = await asyncio.to_thread(
            client.get_body_composition,
            start_date.isoformat(),
            end_date.isoformat(),
        )
    except Exception as e:
        print(f"  body composition error: {e}")
        return 0

    count = 0
    if data and data.get("dateWeightList"):
        async with async_session() as session:
            for entry in data["dateWeightList"]:
                cal_date_str = entry.get("calendarDate")
                if not cal_date_str:
                    continue
                try:
                    cal_date = date.fromisoformat(cal_date_str)
                except (ValueError, TypeError):
                    continue

                weight = entry.get("weight")
                if weight:
                    weight = weight / 1000.0

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
                count += 1
            await session.commit()

    print(f"  body composition: {count} records")
    return count


async def main():
    await create_tables()
    await cleanup_tables()

    print("Logging into Garmin Connect...")
    client = await asyncio.to_thread(get_garmin_client)
    print("Logged in.\n")

    start_date = await get_earliest_activity_date()
    end_date = date.today()
    total_days = (end_date - start_date).days + 1
    print(f"Backfilling from {start_date} to {end_date} ({total_days} days)\n")

    t0 = time.time()

    sleep_count, daily_count, hr_count = await backfill_day_based(client, start_date, end_date)
    body_count = await backfill_body_composition(client, start_date, end_date)

    elapsed = time.time() - t0

    # Update sync_log for all types
    await update_sync_log("sleep", end_date)
    await update_sync_log("daily", end_date)
    await update_sync_log("heart_rate", end_date)
    if body_count > 0:
        await update_sync_log("body", end_date)

    print(f"\nDone in {elapsed:.0f}s")
    print(f"  sleep:            {sleep_count} rows")
    print(f"  daily_summary:    {daily_count} rows")
    print(f"  heart_rate:       {hr_count} rows")
    print(f"  body_composition: {body_count} rows")


if __name__ == "__main__":
    asyncio.run(main())
