from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

from .database import Database, json_text, utc_now


def _walk(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _find(value: Any, *keys: str) -> Any:
    wanted = {key.lower() for key in keys}
    for key, item in _walk(value):
        if key.lower() in wanted and item is not None:
            return item
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _timestamp(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, UTC).isoformat()
        except (ValueError, OSError):
            return None
    return str(value) if value is not None else None


def _arrays_named(payload: Any, pattern: str) -> Iterator[list[Any]]:
    regex = re.compile(pattern, re.I)
    for key, value in _walk(payload):
        if regex.search(key) and isinstance(value, list):
            yield value


def _pairs(arrays: Iterator[list[Any]]) -> Iterator[tuple[Any, Any, Any]]:
    for array in arrays:
        for item in array:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                yield item[0], item[1], item
            elif isinstance(item, dict):
                ts = _find(item, "timestamp", "startGMT", "startTimeGMT", "calendarDate")
                value = _find(item, "value", "heartRate", "stressLevel", "bodyBattery")
                if ts is not None and value is not None:
                    yield ts, value, item


def ingest_daily(db: Database, day: date, source: str, payload: Any, raw_path: Any) -> None:
    db.upsert_daily_payload(day, source, payload, raw_path)
    day_text = day.isoformat()
    summary: dict[str, Any] = {}
    if source in {"stats", "heart_rate"}:
        summary.update(
            resting_hr=_number(_find(payload, "restingHeartRate")),
            average_hr=_number(_find(payload, "averageHeartRate", "wellnessAverageHeartRate")),
            max_hr=_number(_find(payload, "maxHeartRate", "wellnessMaxHeartRate")),
            steps=_find(payload, "totalSteps", "steps"),
            calories=_number(_find(payload, "totalKilocalories", "activeKilocalories", "calories")),
        )
    elif source == "sleep":
        summary.update(
            sleep_seconds=_number(_find(payload, "sleepTimeSeconds", "totalSleepSeconds")),
            sleep_score=_number(_find(payload, "overallScore", "sleepScore")),
        )
    elif source == "hrv":
        summary.update(
            hrv_status=_find(payload, "status", "hrvStatus"),
            hrv_average=_number(_find(payload, "weeklyAvg", "lastNightAvg", "hrvValue")),
        )
    elif source == "stress":
        summary["stress_average"] = _number(_find(payload, "avgStressLevel", "averageStressLevel"))
    elif source == "body_battery":
        summary.update(
            body_battery_high=_number(_find(payload, "charged", "bodyBatteryHigh", "highestValue")),
            body_battery_low=_number(_find(payload, "drained", "bodyBatteryLow", "lowestValue")),
        )
    elif source == "training_readiness":
        summary["training_readiness"] = _number(_find(payload, "score", "trainingReadinessScore"))
    elif source == "training_status":
        summary["training_status"] = _find(
            payload, "trainingStatus", "trainingStatusFeedbackPhrase"
        )
    elif source == "max_metrics":
        summary["vo2max"] = _number(_find(payload, "vo2MaxValue", "vO2MaxValue", "generic"))

    existing = db.connection.execute(
        "SELECT raw_json FROM daily_summary WHERE date=?", (day_text,)
    ).fetchone()
    merged = json.loads(existing[0]) if existing else {}
    merged[source] = payload
    columns = [
        "resting_hr",
        "average_hr",
        "max_hr",
        "steps",
        "calories",
        "sleep_seconds",
        "sleep_score",
        "hrv_status",
        "hrv_average",
        "stress_average",
        "body_battery_high",
        "body_battery_low",
        "training_readiness",
        "training_status",
        "vo2max",
    ]
    values = [summary.get(column) for column in columns]
    db.connection.execute(
        f"INSERT INTO daily_summary(date,{','.join(columns)},raw_json,updated_at) VALUES ({','.join('?' for _ in range(18))}) "
        f"ON CONFLICT(date) DO UPDATE SET "
        + ",".join(
            f"{column}=COALESCE(excluded.{column},daily_summary.{column})" for column in columns
        )
        + ",raw_json=excluded.raw_json,updated_at=excluded.updated_at",
        (day_text, *values, json_text(merged), utc_now()),
    )

    if source == "heart_rate":
        db.connection.execute(
            "DELETE FROM heart_rate_samples WHERE date=? AND source=?", (day_text, source)
        )
        rows = []
        for ts, value, raw in _pairs(_arrays_named(payload, r"heartRateValues|heart.?rate.*array")):
            if _timestamp(ts):
                rows.append((day_text, _timestamp(ts), _number(value), source, json_text(raw)))
        db.executemany(
            "INSERT OR REPLACE INTO heart_rate_samples(date,timestamp,heart_rate,source,raw_json) VALUES (?,?,?,?,?)",
            rows,
        )
    elif source == "stress":
        db.connection.execute("DELETE FROM stress_samples WHERE date=?", (day_text,))
        rows = [
            (day_text, _timestamp(ts), _number(value), json_text(raw))
            for ts, value, raw in _pairs(_arrays_named(payload, r"stressValues|stress.*array"))
            if _timestamp(ts)
        ]
        db.executemany(
            "INSERT OR REPLACE INTO stress_samples(date,timestamp,stress_level,raw_json) VALUES (?,?,?,?)",
            rows,
        )
    elif source == "body_battery":
        db.connection.execute("DELETE FROM body_battery_samples WHERE date=?", (day_text,))
        rows = []
        for ts, value, raw in _pairs(
            _arrays_named(payload, r"bodyBatteryValues|body.?battery.*array")
        ):
            if _timestamp(ts):
                event_type = _find(raw, "eventType", "type") if isinstance(raw, dict) else None
                rows.append(
                    (day_text, _timestamp(ts), _number(value), event_type, source, json_text(raw))
                )
        db.executemany(
            "INSERT OR REPLACE INTO body_battery_samples(date,timestamp,body_battery,event_type,source,raw_json) VALUES (?,?,?,?,?,?)",
            rows,
        )
    elif source == "sleep":
        summary_payload = _find(payload, "dailySleepDTO") or payload
        db.connection.execute(
            "INSERT OR REPLACE INTO sleep_summaries VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                day_text,
                _timestamp(
                    _find(summary_payload, "sleepStartTimestampGMT", "sleepStartTimestampLocal")
                ),
                _timestamp(
                    _find(summary_payload, "sleepEndTimestampGMT", "sleepEndTimestampLocal")
                ),
                _number(_find(summary_payload, "deepSleepSeconds")),
                _number(_find(summary_payload, "lightSleepSeconds")),
                _number(_find(summary_payload, "remSleepSeconds")),
                _number(_find(summary_payload, "awakeSleepSeconds")),
                _number(_find(summary_payload, "overallScore", "sleepScore")),
                _number(_find(summary_payload, "averageRespirationValue", "averageRespiration")),
                json_text(payload),
            ),
        )
        db.connection.execute("DELETE FROM sleep_stages WHERE date=?", (day_text,))
        stages: list[tuple[Any, ...]] = []
        for key, values_ in _walk(payload):
            if "sleeplevels" in key.lower() and isinstance(values_, list):
                for index, item in enumerate(values_):
                    if isinstance(item, dict):
                        stages.append(
                            (
                                day_text,
                                index,
                                _timestamp(_find(item, "startGMT", "startTimeGMT")),
                                _timestamp(_find(item, "endGMT", "endTimeGMT")),
                                _find(item, "activityLevel", "stage", "type"),
                                json_text(item),
                            )
                        )
        db.executemany(
            "INSERT OR REPLACE INTO sleep_stages(date,stage_index,start_time,end_time,stage,raw_json) VALUES (?,?,?,?,?,?)",
            stages,
        )
    elif source == "hrv":
        db.connection.execute("DELETE FROM hrv_samples WHERE date=?", (day_text,))
        readings = _find(payload, "hrvReadings", "readings") or []
        rows = []
        if isinstance(readings, list):
            for index, item in enumerate(readings):
                if isinstance(item, dict):
                    rows.append(
                        (
                            day_text,
                            index,
                            _timestamp(_find(item, "readingTimeGMT", "timestamp")),
                            _number(_find(item, "hrvValue", "value")),
                            json_text(item),
                        )
                    )
        db.executemany(
            "INSERT OR REPLACE INTO hrv_samples(date,sample_index,timestamp,hrv_value,raw_json) VALUES (?,?,?,?,?)",
            rows,
        )

    if source in {
        "training_readiness",
        "training_status",
        "max_metrics",
        "race_predictions",
        "endurance_score",
        "hill_score",
    }:
        db.connection.execute(
            "DELETE FROM training_metrics WHERE date=? AND source=?", (day_text, source)
        )
        rows = []
        for key, value in _walk(payload):
            if isinstance(value, (str, int, float, bool)) or value is None:
                rows.append(
                    (
                        day_text,
                        source,
                        key,
                        _number(value),
                        str(value) if value is not None else None,
                        json_text({key: value}),
                    )
                )
        # Duplicate leaf names are common; keep the last value for this compact V1 table.
        deduped = {row[2]: row for row in rows}
        db.executemany(
            "INSERT OR REPLACE INTO training_metrics(date,source,metric,numeric_value,text_value,raw_json) VALUES (?,?,?,?,?,?)",
            deduped.values(),
        )
