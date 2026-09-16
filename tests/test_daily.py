from datetime import date

from garmin_sync.daily import ingest_daily
from garmin_sync.database import Database


def test_daily_samples_and_summary_are_idempotent(tmp_path):
    db = Database(tmp_path / "garmin.db")
    db.migrate()
    day = date(2026, 9, 15)
    payload = {
        "restingHeartRate": 48,
        "heartRateValues": [[1_757_923_200_000, 52], [1_757_923_260_000, 53]],
    }
    with db.transaction():
        ingest_daily(db, day, "heart_rate", payload, None)
        ingest_daily(db, day, "heart_rate", payload, None)
    assert db.connection.execute("SELECT resting_hr FROM daily_summary").fetchone()[0] == 48
    assert db.connection.execute("SELECT COUNT(*) FROM heart_rate_samples").fetchone()[0] == 2
    assert db.connection.execute("SELECT COUNT(*) FROM daily_payloads").fetchone()[0] == 1
    db.close()
