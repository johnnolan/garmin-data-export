from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _serialise(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "name") and hasattr(value, "value"):
        return value.name
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    return value


def _number(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _coordinate(value: Any, units: str | None) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if units == "semicircles" or abs(float(number)) > 180:
        return float(number) * (180.0 / 2**31)
    return float(number)


@dataclass
class ParsedFit:
    sessions: list[tuple[Any, ...]] = field(default_factory=list)
    laps: list[tuple[Any, ...]] = field(default_factory=list)
    records: list[tuple[Any, ...]] = field(default_factory=list)
    events: list[tuple[Any, ...]] = field(default_factory=list)
    messages: list[tuple[Any, ...]] = field(default_factory=list)


def parse_fit(path: Path, activity_id: str) -> ParsedFit:
    try:
        import fitdecode
    except ImportError as error:  # pragma: no cover - installation error
        raise RuntimeError("fitdecode is required to import FIT files") from error

    result = ParsedFit()
    counts: dict[str, int] = {}
    current_session = 0
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.WARN) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            name = str(frame.name)
            index = counts.get(name, 0)
            counts[name] = index + 1
            fields: dict[str, Any] = {}
            units: dict[str, str] = {}
            for item in frame.fields:
                fields[item.name] = _serialise(item.value)
                if item.units:
                    units[item.name] = item.units
            raw = dict(fields)
            if units:
                raw["_units"] = units
            encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
            timestamp = fields.get("timestamp")
            if name == "session":
                current_session = index
                result.sessions.append(
                    (
                        activity_id,
                        index,
                        fields.get("start_time"),
                        timestamp,
                        fields.get("sport"),
                        fields.get("sub_sport"),
                        _number(fields.get("total_elapsed_time")),
                        _number(fields.get("total_timer_time")),
                        _number(fields.get("total_distance")),
                        _number(fields.get("avg_speed")),
                        _number(fields.get("max_speed")),
                        _number(fields.get("avg_heart_rate")),
                        _number(fields.get("max_heart_rate")),
                        _number(fields.get("avg_cadence")),
                        _number(fields.get("total_ascent")),
                        _number(fields.get("total_descent")),
                        _number(fields.get("total_calories")),
                        encoded,
                    )
                )
            elif name == "lap":
                result.laps.append(
                    (
                        activity_id,
                        current_session,
                        index,
                        fields.get("start_time"),
                        timestamp,
                        _number(fields.get("total_elapsed_time")),
                        _number(fields.get("total_timer_time")),
                        _number(fields.get("total_distance")),
                        _number(fields.get("avg_speed")),
                        _number(fields.get("max_speed")),
                        _number(fields.get("avg_heart_rate")),
                        _number(fields.get("max_heart_rate")),
                        _number(fields.get("avg_cadence")),
                        _number(fields.get("total_ascent")),
                        _number(fields.get("total_descent")),
                        _number(fields.get("total_calories")),
                        encoded,
                    )
                )
            elif name == "record":
                result.records.append(
                    (
                        activity_id,
                        timestamp,
                        index,
                        _coordinate(fields.get("position_lat"), units.get("position_lat")),
                        _coordinate(fields.get("position_long"), units.get("position_long")),
                        _number(fields.get("altitude")),
                        _number(fields.get("enhanced_altitude")),
                        _number(fields.get("heart_rate")),
                        _number(fields.get("cadence")),
                        _number(fields.get("fractional_cadence")),
                        _number(fields.get("speed")),
                        _number(fields.get("enhanced_speed")),
                        _number(fields.get("distance")),
                        _number(fields.get("power")),
                        _number(fields.get("temperature")),
                        _number(fields.get("grade")),
                        _number(fields.get("vertical_speed")),
                        _number(fields.get("vertical_oscillation")),
                        _number(fields.get("ground_contact_time")),
                        _number(fields.get("ground_contact_balance")),
                        _number(fields.get("stance_time")),
                        _number(fields.get("stance_time_balance")),
                        _number(fields.get("step_length")),
                        _number(fields.get("respiration_rate")),
                        _number(fields.get("performance_condition")),
                        _number(fields.get("accumulated_power")),
                        _number(fields.get("calories")),
                        encoded,
                    )
                )
            elif name == "event":
                result.events.append(
                    (
                        activity_id,
                        index,
                        timestamp,
                        fields.get("event"),
                        fields.get("event_type"),
                        str(fields.get("data")) if fields.get("data") is not None else None,
                        encoded,
                    )
                )
            else:
                result.messages.append((activity_id, name, index, timestamp, encoded))
    return result
