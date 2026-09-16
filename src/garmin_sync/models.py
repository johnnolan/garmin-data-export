from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class SyncStats:
    activities_found: int = 0
    activities_downloaded: int = 0
    activities_skipped: int = 0
    daily_records_processed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncWindow:
    mode: str
    start: date | None
    end: date
