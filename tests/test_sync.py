from datetime import date

from garmin_sync.client import GarminReader
from garmin_sync.config import Config
from garmin_sync.database import Database
from garmin_sync.raw_store import RawStore
from garmin_sync.sync import Synchronizer, date_range, rebuild, recent_window


class FakeApi:
    def get_activities_by_date(self, start, end):
        return [{"activityId": 99, "startTimeLocal": "2026-09-15 09:00:00"}]

    def get_activity(self, activity_id):
        return {"activityId": 99, "activityName": "Run", "distance": 5000}


def config(tmp_path):
    return Config(
        tmp_path / "data",
        tmp_path / "data" / "garmin.db",
        tmp_path / "tokens",
        request_delay_seconds=0,
        store_fit=False,
    )


def test_recent_date_calculation():
    window = recent_window(7, date(2026, 9, 16))
    assert window.start == date(2026, 9, 10)
    assert window.end == date(2026, 9, 16)


def test_rerunning_import_does_not_duplicate(tmp_path):
    cfg = config(tmp_path)
    db = Database(cfg.database)
    db.migrate()
    raw = RawStore(cfg.data_directory / "raw")
    reader = GarminReader(FakeApi(), delay=0)
    sync = Synchronizer(cfg, db, raw, reader)
    # Avoid optional endpoint noise; this test concerns activity idempotency.
    reader.daily_sources = lambda day: iter(())
    window = date_range(date(2026, 9, 15), date(2026, 9, 15))
    assert sync.run(window)[1] == "success"
    assert sync.run(window)[1] == "success"
    assert db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
    db.close()


def test_partial_activity_failure_is_recorded_and_other_activity_continues(tmp_path):
    class PartialApi(FakeApi):
        def get_activities_by_date(self, start, end):
            return [{"activityId": 1}, {"activityId": 2}]

        def get_activity(self, activity_id):
            if activity_id == "1":
                raise RuntimeError("temporary failure")
            return {"activityId": 2, "activityName": "Walk"}

    cfg = config(tmp_path)
    db = Database(cfg.database)
    db.migrate()
    reader = GarminReader(PartialApi(), delay=0)
    reader.daily_sources = lambda day: iter(())
    _, status = Synchronizer(cfg, db, RawStore(cfg.data_directory / "raw"), reader).run(
        date_range(date(2026, 9, 15), date(2026, 9, 15))
    )
    assert status == "partial"
    assert db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 2
    db.close()


def test_rebuild_uses_only_raw_files(tmp_path):
    cfg = config(tmp_path)
    raw = RawStore(cfg.data_directory / "raw")
    raw.store_activity_json(
        "7",
        2026,
        {"activityId": 7, "activityName": "Recovered", "startTimeLocal": "2026-09-15"},
    )
    raw.store_daily(date(2026, 9, 15), "stats", {"totalSteps": 1234})
    db = Database(cfg.database)
    db.migrate()
    stats = rebuild(cfg, db, raw)
    assert stats.errors == []
    assert db.connection.execute("SELECT name FROM activities").fetchone()[0] == "Recovered"
    assert db.connection.execute("SELECT steps FROM daily_summary").fetchone()[0] == 1234
    db.close()
