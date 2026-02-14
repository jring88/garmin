from datetime import date, datetime

from pydantic import BaseModel


class ActivityOut(BaseModel):
    activity_id: int
    activity_type: str | None = None
    activity_name: str | None = None
    start_time: datetime | None = None
    duration_seconds: float | None = None
    distance_meters: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_speed: float | None = None
    max_speed: float | None = None
    calories: float | None = None
    cadence: float | None = None
    vo2max: float | None = None
    training_effect_aerobic: float | None = None
    training_effect_anaerobic: float | None = None
    elevation_gain: float | None = None

    class Config:
        from_attributes = True


class SleepOut(BaseModel):
    calendar_date: date
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    total_sleep_seconds: int | None = None
    deep_seconds: int | None = None
    light_seconds: int | None = None
    rem_seconds: int | None = None
    awake_seconds: int | None = None
    sleep_score: int | None = None
    avg_respiration: float | None = None
    avg_spo2: float | None = None
    resting_hr: int | None = None

    class Config:
        from_attributes = True


class DailySummaryOut(BaseModel):
    calendar_date: date
    steps: int | None = None
    total_distance_meters: float | None = None
    active_calories: float | None = None
    total_calories: float | None = None
    resting_hr: int | None = None
    max_hr: int | None = None
    avg_stress: int | None = None
    max_stress: int | None = None
    body_battery_high: int | None = None
    body_battery_low: int | None = None
    floors_climbed: int | None = None
    intensity_minutes: int | None = None

    class Config:
        from_attributes = True


class HeartRateOut(BaseModel):
    calendar_date: date
    resting_hr: int | None = None
    max_hr: int | None = None
    min_hr: int | None = None

    class Config:
        from_attributes = True


class BodyCompositionOut(BaseModel):
    calendar_date: date
    weight_kg: float | None = None
    bmi: float | None = None
    body_fat_pct: float | None = None
    muscle_mass_kg: float | None = None
    bone_mass_kg: float | None = None
    body_water_pct: float | None = None

    class Config:
        from_attributes = True


class JournalCreate(BaseModel):
    entry_date: date
    category: str = "general"
    content: str = ""
    rating: int | None = None
    tags: str | None = None


class JournalUpdate(BaseModel):
    entry_date: date | None = None
    category: str | None = None
    content: str | None = None
    rating: int | None = None
    tags: str | None = None


class JournalOut(BaseModel):
    id: int
    entry_date: date
    category: str
    content: str
    rating: int | None = None
    tags: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SyncStatusOut(BaseModel):
    data_type: str
    last_synced_date: date | None = None
    last_sync_at: datetime | None = None
    status: str
    error_message: str | None = None
    progress: str | None = None

    class Config:
        from_attributes = True


class DashboardOut(BaseModel):
    activities: list[ActivityOut]
    sleep: list[SleepOut]
    daily: list[DailySummaryOut]
    heart_rate: list[HeartRateOut]
    body: list[BodyCompositionOut]
