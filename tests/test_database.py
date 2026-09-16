from __future__ import annotations

import json

from garmin_sync.database import Database
from garmin_sync.fit_parser import ParsedFit


def activity(activity_id: int = 42, distance: float = 1000) -> dict:
    return {
        "activityId": activity_id,
        "activityName": "Trail run",
        "activityType": {"typeKey": "trail_running"},
        "startTimeLocal": "2026-09-15 07:00:00",
        "distance": distance,
        "averageHR": 140,
    }


def test_database_creation_and_activity_upsert_is_idempotent(tmp_path):
    db = Database(tmp_path / "garmin.db")
    db.migrate()
    with db.transaction():
        db.upsert_activity(activity(), None)
        db.upsert_activity(activity(distance=1200), None)
    row = db.connection.execute("SELECT COUNT(*) count, distance_m FROM activities").fetchone()
    assert row["count"] == 1
    assert row["distance_m"] == 1200
    assert db.connection.execute("SELECT version FROM schema_version").fetchone()[0] == 1
    db.close()


def test_fit_rows_are_replaced_in_bulk(tmp_path):
    db = Database(tmp_path / "garmin.db")
    db.migrate()
    with db.transaction():
        db.upsert_activity(activity(), None)
    raw = json.dumps({"timestamp": "2026-09-15T07:00:00"})
    parsed = ParsedFit(
        records=[
            (
                "42",
                "2026-09-15T07:00:00",
                0,
                None,
                None,
                10,
                10,
                140,
                80,
                None,
                3,
                3,
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                raw,
            )
        ]
    )
    db.replace_fit_rows("42", parsed)
    db.replace_fit_rows("42", parsed)
    assert db.connection.execute("SELECT COUNT(*) FROM activity_records").fetchone()[0] == 1
    db.close()
