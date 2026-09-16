from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import date
from typing import Any


class GarminReader:
    """Small read-only boundary around documented garminconnect methods."""

    def __init__(self, api: Any, delay: float = 0.5, page_size: int = 100) -> None:
        self.api = api
        self.delay = delay
        self.page_size = page_size

    def _pause(self) -> None:
        if self.delay:
            time.sleep(self.delay)

    def iter_all_activities(self) -> Iterator[dict[str, Any]]:
        start = 0
        while True:
            page = self.api.get_activities(start, self.page_size)
            if not page:
                return
            yield from page
            start += len(page)
            if len(page) < self.page_size:
                return
            self._pause()

    def activities_by_date(self, start: date, end: date) -> list[dict[str, Any]]:
        return self.api.get_activities_by_date(start.isoformat(), end.isoformat())

    def activity(self, activity_id: str) -> dict[str, Any]:
        value = self.api.get_activity(activity_id)
        self._pause()
        return value

    def original_activity(self, activity_id: str) -> bytes:
        from garminconnect import Garmin

        value = self.api.download_activity(
            activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
        )
        self._pause()
        return value

    def daily_sources(self, day: date) -> Iterator[tuple[str, Any]]:
        day_text = day.isoformat()
        calls = (
            ("stats", "get_stats", (day_text,)),
            ("heart_rate", "get_heart_rates", (day_text,)),
            ("sleep", "get_sleep_data", (day_text,)),
            ("stress", "get_stress_data", (day_text,)),
            ("hrv", "get_hrv_data", (day_text,)),
            ("body_battery", "get_body_battery", (day_text, day_text)),
            ("training_readiness", "get_training_readiness", (day_text,)),
            ("training_status", "get_training_status", (day_text,)),
            ("max_metrics", "get_max_metrics", (day_text,)),
            ("race_predictions", "get_race_predictions", (day_text, day_text, "daily")),
            ("endurance_score", "get_endurance_score", (day_text, day_text)),
            ("hill_score", "get_hill_score", (day_text, day_text)),
            ("respiration", "get_respiration_data", (day_text,)),
            ("spo2", "get_spo2_data", (day_text,)),
        )
        for source, method_name, arguments in calls:
            method = getattr(self.api, method_name, None)
            if method is None:
                yield source, NotImplementedError(f"garminconnect has no {method_name}")
                continue
            try:
                value = method(*arguments)
            except Exception as error:  # optional endpoints differ by account/device
                yield source, error
            else:
                if value not in (None, {}, []):
                    yield source, value
            self._pause()
