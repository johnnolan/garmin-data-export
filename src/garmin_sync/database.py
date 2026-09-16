from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    mode TEXT NOT NULL,
    requested_start_date TEXT,
    requested_end_date TEXT,
    status TEXT NOT NULL,
    activities_found INTEGER NOT NULL DEFAULT 0,
    activities_downloaded INTEGER NOT NULL DEFAULT 0,
    activities_skipped INTEGER NOT NULL DEFAULT 0,
    daily_records_processed INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    error_details_json TEXT
);
CREATE TABLE IF NOT EXISTS activities (
    garmin_activity_id TEXT PRIMARY KEY,
    name TEXT,
    activity_type TEXT,
    sport_type TEXT,
    start_time_local TEXT,
    start_time_utc TEXT,
    distance_m REAL,
    duration_seconds REAL,
    moving_duration_seconds REAL,
    elapsed_duration_seconds REAL,
    elevation_gain_m REAL,
    elevation_loss_m REAL,
    average_speed REAL,
    max_speed REAL,
    average_hr REAL,
    max_hr REAL,
    average_cadence REAL,
    calories REAL,
    training_effect REAL,
    aerobic_training_effect REAL,
    anaerobic_training_effect REAL,
    activity_training_load REAL,
    vo2max REAL,
    raw_json TEXT NOT NULL,
    raw_json_path TEXT,
    original_path TEXT,
    fit_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type);
CREATE INDEX IF NOT EXISTS idx_activities_start ON activities(start_time_local);

CREATE TABLE IF NOT EXISTS activity_sessions (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(garmin_activity_id) ON DELETE CASCADE,
    session_index INTEGER NOT NULL,
    start_time TEXT,
    timestamp TEXT,
    sport TEXT,
    sub_sport TEXT,
    elapsed_time_seconds REAL,
    timer_time_seconds REAL,
    distance_m REAL,
    avg_speed_mps REAL,
    max_speed_mps REAL,
    avg_hr REAL,
    max_hr REAL,
    avg_cadence REAL,
    ascent_m REAL,
    descent_m REAL,
    calories REAL,
    raw_json TEXT NOT NULL,
    UNIQUE(activity_id, session_index)
);
CREATE TABLE IF NOT EXISTS activity_laps (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(garmin_activity_id) ON DELETE CASCADE,
    session_index INTEGER,
    lap_index INTEGER NOT NULL,
    start_time TEXT,
    end_time TEXT,
    elapsed_time_seconds REAL,
    timer_time_seconds REAL,
    distance_m REAL,
    avg_speed_mps REAL,
    max_speed_mps REAL,
    avg_hr REAL,
    max_hr REAL,
    avg_cadence REAL,
    ascent_m REAL,
    descent_m REAL,
    calories REAL,
    raw_json TEXT NOT NULL,
    UNIQUE(activity_id, lap_index)
);
CREATE TABLE IF NOT EXISTS activity_records (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(garmin_activity_id) ON DELETE CASCADE,
    timestamp TEXT,
    sequence_number INTEGER NOT NULL,
    latitude REAL,
    longitude REAL,
    altitude_m REAL,
    enhanced_altitude_m REAL,
    heart_rate REAL,
    cadence REAL,
    fractional_cadence REAL,
    speed_mps REAL,
    enhanced_speed_mps REAL,
    distance_m REAL,
    power_w REAL,
    temperature_c REAL,
    grade REAL,
    vertical_speed REAL,
    vertical_oscillation REAL,
    ground_contact_time REAL,
    ground_contact_balance REAL,
    stance_time REAL,
    stance_time_balance REAL,
    step_length REAL,
    respiration_rate REAL,
    performance_condition REAL,
    accumulated_power REAL,
    calories REAL,
    raw_json TEXT NOT NULL,
    UNIQUE(activity_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS idx_records_activity ON activity_records(activity_id);
CREATE INDEX IF NOT EXISTS idx_records_timestamp ON activity_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_records_activity_timestamp ON activity_records(activity_id, timestamp);
CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(garmin_activity_id) ON DELETE CASCADE,
    event_index INTEGER NOT NULL,
    timestamp TEXT,
    event TEXT,
    event_type TEXT,
    data TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(activity_id, event_index)
);
CREATE TABLE IF NOT EXISTS fit_messages (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(garmin_activity_id) ON DELETE CASCADE,
    message_type TEXT NOT NULL,
    message_index INTEGER NOT NULL,
    timestamp TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(activity_id, message_type, message_index)
);
CREATE INDEX IF NOT EXISTS idx_fit_messages_activity_type ON fit_messages(activity_id, message_type);

CREATE TABLE IF NOT EXISTS daily_payloads (
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    raw_json_path TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(date, source)
);
CREATE TABLE IF NOT EXISTS daily_summary (
    date TEXT PRIMARY KEY,
    resting_hr REAL,
    average_hr REAL,
    max_hr REAL,
    steps INTEGER,
    calories REAL,
    sleep_seconds REAL,
    sleep_score REAL,
    hrv_status TEXT,
    hrv_average REAL,
    stress_average REAL,
    body_battery_high REAL,
    body_battery_low REAL,
    training_readiness REAL,
    training_status TEXT,
    vo2max REAL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON daily_summary(date);
CREATE TABLE IF NOT EXISTS heart_rate_samples (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, timestamp TEXT NOT NULL,
    heart_rate REAL, source TEXT, raw_json TEXT NOT NULL, UNIQUE(date, timestamp, source)
);
CREATE INDEX IF NOT EXISTS idx_hr_samples_timestamp ON heart_rate_samples(timestamp);
CREATE TABLE IF NOT EXISTS stress_samples (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, timestamp TEXT NOT NULL,
    stress_level REAL, raw_json TEXT NOT NULL, UNIQUE(date, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_stress_samples_timestamp ON stress_samples(timestamp);
CREATE TABLE IF NOT EXISTS body_battery_samples (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, timestamp TEXT NOT NULL,
    body_battery REAL, event_type TEXT, source TEXT, raw_json TEXT NOT NULL,
    UNIQUE(date, timestamp, event_type)
);
CREATE INDEX IF NOT EXISTS idx_battery_samples_timestamp ON body_battery_samples(timestamp);
CREATE TABLE IF NOT EXISTS sleep_summaries (
    date TEXT PRIMARY KEY, sleep_start TEXT, sleep_end TEXT, deep_seconds REAL,
    light_seconds REAL, rem_seconds REAL, awake_seconds REAL, sleep_score REAL,
    respiration REAL, raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sleep_stages (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, stage_index INTEGER NOT NULL,
    start_time TEXT, end_time TEXT, stage TEXT, raw_json TEXT NOT NULL,
    UNIQUE(date, stage_index)
);
CREATE TABLE IF NOT EXISTS hrv_samples (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, sample_index INTEGER NOT NULL,
    timestamp TEXT, hrv_value REAL, raw_json TEXT NOT NULL, UNIQUE(date, sample_index)
);
CREATE INDEX IF NOT EXISTS idx_hrv_samples_timestamp ON hrv_samples(timestamp);
CREATE TABLE IF NOT EXISTS training_metrics (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL,
    numeric_value REAL, text_value TEXT, raw_json TEXT NOT NULL,
    UNIQUE(date, source, metric)
);
CREATE INDEX IF NOT EXISTS idx_training_metrics_date ON training_metrics(date);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")

    def close(self) -> None:
        self.connection.close()

    def migrate(self) -> None:
        with self.connection:
            self.connection.executescript(SCHEMA)
            self.connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection:
            yield self.connection

    def start_sync(self, mode: str, start: date | None, end: date) -> int:
        cursor = self.connection.execute(
            "INSERT INTO sync_runs(started_at, mode, requested_start_date, requested_end_date, status) "
            "VALUES (?, ?, ?, ?, 'running')",
            (utc_now(), mode, start.isoformat() if start else None, end.isoformat()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_sync(self, run_id: int, status: str, stats: Any) -> None:
        self.connection.execute(
            "UPDATE sync_runs SET completed_at=?, status=?, activities_found=?, "
            "activities_downloaded=?, activities_skipped=?, daily_records_processed=?, "
            "errors=?, error_details_json=? WHERE id=?",
            (
                utc_now(),
                status,
                stats.activities_found,
                stats.activities_downloaded,
                stats.activities_skipped,
                stats.daily_records_processed,
                len(stats.errors),
                json_text(stats.errors),
                run_id,
            ),
        )
        self.connection.commit()

    def upsert_activity(
        self,
        activity: dict[str, Any],
        raw_path: Path | None,
        original_path: Path | None = None,
        fit_path: Path | None = None,
    ) -> str:
        activity_id = str(activity["activityId"])
        kind = activity.get("activityType") or {}
        sport = activity.get("sportType") or {}
        now = utc_now()
        values = (
            activity_id,
            activity.get("activityName") or activity.get("name"),
            kind.get("typeKey") if isinstance(kind, dict) else kind,
            sport.get("sportTypeKey") if isinstance(sport, dict) else sport,
            activity.get("startTimeLocal"),
            activity.get("startTimeGMT") or activity.get("startTimeUTC"),
            activity.get("distance"),
            activity.get("duration"),
            activity.get("movingDuration"),
            activity.get("elapsedDuration"),
            activity.get("elevationGain"),
            activity.get("elevationLoss"),
            activity.get("averageSpeed"),
            activity.get("maxSpeed"),
            activity.get("averageHR"),
            activity.get("maxHR"),
            activity.get("averageRunningCadenceInStepsPerMinute")
            or activity.get("averageBikingCadenceInRevPerMinute"),
            activity.get("calories"),
            activity.get("trainingEffect"),
            activity.get("aerobicTrainingEffect"),
            activity.get("anaerobicTrainingEffect"),
            activity.get("activityTrainingLoad"),
            activity.get("vO2MaxValue") or activity.get("vo2MaxValue"),
            json_text(activity),
            str(raw_path) if raw_path else None,
            str(original_path) if original_path else None,
            str(fit_path) if fit_path else None,
            now,
            now,
        )
        self.connection.execute(
            """INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(garmin_activity_id) DO UPDATE SET
              name=excluded.name, activity_type=excluded.activity_type, sport_type=excluded.sport_type,
              start_time_local=excluded.start_time_local, start_time_utc=excluded.start_time_utc,
              distance_m=excluded.distance_m, duration_seconds=excluded.duration_seconds,
              moving_duration_seconds=excluded.moving_duration_seconds,
              elapsed_duration_seconds=excluded.elapsed_duration_seconds,
              elevation_gain_m=excluded.elevation_gain_m, elevation_loss_m=excluded.elevation_loss_m,
              average_speed=excluded.average_speed, max_speed=excluded.max_speed,
              average_hr=excluded.average_hr, max_hr=excluded.max_hr,
              average_cadence=excluded.average_cadence, calories=excluded.calories,
              training_effect=excluded.training_effect,
              aerobic_training_effect=excluded.aerobic_training_effect,
              anaerobic_training_effect=excluded.anaerobic_training_effect,
              activity_training_load=excluded.activity_training_load, vo2max=excluded.vo2max,
              raw_json=excluded.raw_json, raw_json_path=excluded.raw_json_path,
              original_path=COALESCE(excluded.original_path, activities.original_path),
              fit_path=COALESCE(excluded.fit_path, activities.fit_path), updated_at=excluded.updated_at""",
            values,
        )
        return activity_id

    def replace_fit_rows(self, activity_id: str, parsed: Any) -> None:
        with self.transaction() as connection:
            for table in (
                "activity_sessions",
                "activity_laps",
                "activity_records",
                "activity_events",
                "fit_messages",
            ):
                connection.execute(f"DELETE FROM {table} WHERE activity_id=?", (activity_id,))
            connection.executemany(
                "INSERT INTO activity_sessions(activity_id,session_index,start_time,timestamp,sport,sub_sport,elapsed_time_seconds,timer_time_seconds,distance_m,avg_speed_mps,max_speed_mps,avg_hr,max_hr,avg_cadence,ascent_m,descent_m,calories,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                parsed.sessions,
            )
            connection.executemany(
                "INSERT INTO activity_laps(activity_id,session_index,lap_index,start_time,end_time,elapsed_time_seconds,timer_time_seconds,distance_m,avg_speed_mps,max_speed_mps,avg_hr,max_hr,avg_cadence,ascent_m,descent_m,calories,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                parsed.laps,
            )
            connection.executemany(
                "INSERT INTO activity_records(activity_id,timestamp,sequence_number,latitude,longitude,altitude_m,enhanced_altitude_m,heart_rate,cadence,fractional_cadence,speed_mps,enhanced_speed_mps,distance_m,power_w,temperature_c,grade,vertical_speed,vertical_oscillation,ground_contact_time,ground_contact_balance,stance_time,stance_time_balance,step_length,respiration_rate,performance_condition,accumulated_power,calories,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                parsed.records,
            )
            connection.executemany(
                "INSERT INTO activity_events(activity_id,event_index,timestamp,event,event_type,data,raw_json) VALUES (?,?,?,?,?,?,?)",
                parsed.events,
            )
            connection.executemany(
                "INSERT INTO fit_messages(activity_id,message_type,message_index,timestamp,raw_json) VALUES (?,?,?,?,?)",
                parsed.messages,
            )

    def upsert_daily_payload(self, day: date, source: str, payload: Any, path: Path | None) -> None:
        self.connection.execute(
            "INSERT INTO daily_payloads VALUES (?,?,?,?,?) ON CONFLICT(date,source) DO UPDATE SET "
            "raw_json=excluded.raw_json, raw_json_path=excluded.raw_json_path, updated_at=excluded.updated_at",
            (day.isoformat(), source, json_text(payload), str(path) if path else None, utc_now()),
        )

    def status(self) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT COUNT(*) count, MIN(start_time_local) oldest, MAX(start_time_local) newest FROM activities"
        ).fetchone()
        daily = self.connection.execute(
            "SELECT MIN(date) oldest, MAX(date) newest FROM daily_summary"
        ).fetchone()
        last = self.connection.execute(
            "SELECT completed_at FROM sync_runs WHERE status='success' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "activity_count": row["count"],
            "oldest_activity": row["oldest"],
            "newest_activity": row["newest"],
            "oldest_daily": daily["oldest"],
            "newest_daily": daily["newest"],
            "last_successful_sync": last[0] if last else None,
        }

    def clear_derived_data(self) -> None:
        with self.transaction() as connection:
            for table in (
                "activity_sessions",
                "activity_laps",
                "activity_records",
                "activity_events",
                "fit_messages",
                "heart_rate_samples",
                "stress_samples",
                "body_battery_samples",
                "sleep_stages",
                "sleep_summaries",
                "hrv_samples",
                "training_metrics",
                "daily_summary",
                "daily_payloads",
                "activities",
            ):
                connection.execute(f"DELETE FROM {table}")

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        self.connection.executemany(sql, rows)
