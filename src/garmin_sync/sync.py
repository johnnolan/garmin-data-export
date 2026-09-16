from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from garminconnect import GarminConnectNotFoundError

from .client import GarminReader
from .config import Config
from .daily import ingest_daily
from .database import Database
from .fit_parser import parse_fit
from .models import SyncStats, SyncWindow
from .raw_store import RawStore

LOG = logging.getLogger(__name__)


def recent_window(days: int, today: date | None = None) -> SyncWindow:
    if days < 1:
        raise ValueError("days must be at least 1")
    end = today or date.today()
    return SyncWindow("recent", end - timedelta(days=days - 1), end)


def date_range(start: date, end: date) -> SyncWindow:
    if start > end:
        raise ValueError("--from must not be after --to")
    return SyncWindow("range", start, end)


def all_window(today: date | None = None) -> SyncWindow:
    return SyncWindow("all", None, today or date.today())


def days_inclusive(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def activity_year(activity: dict[str, Any]) -> int:
    value = activity.get("startTimeLocal") or activity.get("startTimeGMT")
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return date.today().year


class Synchronizer:
    def __init__(self, config: Config, db: Database, raw: RawStore, reader: GarminReader) -> None:
        self.config, self.db, self.raw, self.reader = config, db, raw, reader

    def run(self, window: SyncWindow) -> tuple[SyncStats, str]:
        stats = SyncStats()
        run_id = self.db.start_sync(window.mode, window.start, window.end)
        LOG.info("sync start mode=%s start=%s end=%s", window.mode, window.start, window.end)
        earliest: date | None = window.start or self.config.historical_start_date
        try:
            activities = (
                self.reader.iter_all_activities()
                if window.mode == "all"
                else iter(
                    self.reader.activities_by_date(window.start, window.end)  # type: ignore[arg-type]
                )
            )
            for summary in activities:
                stats.activities_found += 1
                value = summary.get("startTimeLocal") or summary.get("startTimeGMT")
                if value:
                    try:
                        candidate = date.fromisoformat(str(value)[:10])
                        earliest = min(earliest, candidate) if earliest else candidate
                    except ValueError:
                        pass
                self._activity(summary, stats)
        except Exception as error:
            stats.errors.append(f"activity listing failed: {error}")
            LOG.exception("activity listing failed")

        if earliest is not None:
            for day in days_inclusive(earliest, window.end):
                self._daily(day, stats)
        status = "success" if not stats.errors else "partial"
        self.db.finish_sync(run_id, status, stats)
        LOG.info(
            "sync complete status=%s found=%d downloaded=%d skipped=%d daily=%d errors=%d",
            status,
            stats.activities_found,
            stats.activities_downloaded,
            stats.activities_skipped,
            stats.daily_records_processed,
            len(stats.errors),
        )
        return stats, status

    def _activity(self, summary: dict[str, Any], stats: SyncStats) -> None:
        activity_id = str(summary.get("activityId", ""))
        if not activity_id:
            stats.errors.append("activity without activityId")
            return
        activity = summary
        try:
            detail = self.reader.activity(activity_id)
            # The list response sometimes contains fields absent from the detail endpoint.
            activity = {**summary, **detail}
        except Exception as error:
            stats.errors.append(f"activity {activity_id} details: {error}")
            LOG.exception("failed activity details id=%s; retaining list metadata", activity_id)
        try:
            year = activity_year(activity)
            raw_path = (
                self.raw.store_activity_json(activity_id, year, activity)
                if self.config.store_json
                else None
            )
            original_path = fit_path = None
            if self.config.store_fit:
                directory = self.raw.activity_directory(activity_id, year)
                existing_fit = list(directory.glob("activity*.fit"))
                existing_original = list(directory.glob("activity.zip"))
                if existing_fit:
                    fit_path = _latest(existing_fit)
                    original_path = _latest(existing_original) if existing_original else fit_path
                    stats.activities_skipped += 1
                else:
                    try:
                        content = self.reader.original_activity(activity_id)
                        original_path, fit_path = self.raw.store_activity_original(
                            activity_id, year, content
                        )
                        stats.activities_downloaded += 1
                    except Exception as error:
                        if isinstance(error, GarminConnectNotFoundError):
                            LOG.warning("no original activity export id=%s", activity_id)
                            stats.activities_skipped += 1
                        else:
                            stats.errors.append(f"activity {activity_id} download: {error}")
                            LOG.exception("failed activity download id=%s", activity_id)
            with self.db.transaction():
                self.db.upsert_activity(activity, raw_path, original_path, fit_path)
            if fit_path:
                try:
                    parsed = parse_fit(fit_path, activity_id)
                    self.db.replace_fit_rows(activity_id, parsed)
                except Exception as error:
                    stats.errors.append(f"activity {activity_id} FIT: {error}")
                    LOG.exception("failed FIT ingestion id=%s", activity_id)
            elif not self.config.store_fit:
                stats.activities_skipped += 1
        except Exception as error:
            message = f"activity {activity_id} storage: {error}"
            stats.errors.append(message)
            LOG.exception("failed activity storage id=%s", activity_id)

    def _daily(self, day: date, stats: SyncStats) -> None:
        processed = 0
        for source, value in self.reader.daily_sources(day):
            if isinstance(value, Exception):
                LOG.warning(
                    "optional daily metric unavailable date=%s source=%s error=%s",
                    day,
                    source,
                    value,
                )
                continue
            try:
                path = self.raw.store_daily(day, source, value) if self.config.store_json else None
                with self.db.transaction():
                    ingest_daily(self.db, day, source, value, path)
                processed += 1
            except Exception:
                LOG.exception("failed optional daily metric date=%s source=%s", day, source)
        if processed:
            stats.daily_records_processed += 1


def _latest(paths: list[Path]) -> Path:
    return max(paths, key=lambda path: path.stat().st_mtime_ns)


def rebuild(config: Config, db: Database, raw: RawStore) -> SyncStats:
    stats = SyncStats()
    db.clear_derived_data()
    for directory in sorted(raw.activities.glob("*/*")):
        if not directory.is_dir():
            continue
        activity_id = directory.name
        json_paths = list(directory.glob("activity*.json"))
        if not json_paths:
            stats.errors.append(f"missing activity JSON: {directory}")
            continue
        try:
            json_path = _latest(json_paths)
            activity = json.loads(json_path.read_text(encoding="utf-8"))
            fit_paths = list(directory.glob("activity*.fit"))
            originals = list(directory.glob("activity.zip")) or fit_paths
            fit_path = _latest(fit_paths) if fit_paths else None
            with db.transaction():
                db.upsert_activity(
                    activity, json_path, _latest(originals) if originals else None, fit_path
                )
            if fit_path:
                db.replace_fit_rows(activity_id, parse_fit(fit_path, activity_id))
            stats.activities_found += 1
        except Exception as error:
            stats.errors.append(f"rebuild activity {activity_id}: {error}")
            LOG.exception("rebuild failed activity=%s", activity_id)
    grouped: dict[tuple[date, str], list[Path]] = {}
    for path in raw.daily.glob("*/*/*/*.json"):
        try:
            day = date.fromisoformat(path.parent.name)
        except ValueError:
            continue
        source = re.sub(r"-[0-9a-f]{12}$", "", path.stem)
        grouped.setdefault((day, source), []).append(path)
    for (day, source), paths in sorted(grouped.items()):
        try:
            path = _latest(paths)
            payload = json.loads(path.read_text(encoding="utf-8"))
            with db.transaction():
                ingest_daily(db, day, source, payload, path)
            stats.daily_records_processed += 1
        except Exception as error:
            stats.errors.append(f"rebuild daily {day}/{source}: {error}")
    return stats
