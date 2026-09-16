from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Config:
    data_directory: Path
    database: Path
    token_store: Path
    default_days: int = 7
    request_delay_seconds: float = 0.5
    activity_page_size: int = 100
    historical_start_date: date | None = None
    store_json: bool = True
    store_fit: bool = True


def _path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_config(path: Path | None = None) -> Config:
    config_path = (path or Path("config.yaml")).expanduser().resolve()
    values: dict[str, Any] = {}
    base = Path.cwd()
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("configuration root must be a mapping")
        values = loaded
        base = config_path.parent
    sync = values.get("sync") or {}
    raw = values.get("raw") or {}
    data_directory = _path(str(values.get("data_directory", "./data")), base)
    database_value = values.get("database")
    database = _path(str(database_value), base) if database_value else data_directory / "garmin.db"
    return Config(
        data_directory=data_directory,
        database=database,
        token_store=_path(str(values.get("token_store", "~/.garminconnect")), base),
        default_days=int(sync.get("default_days", 7)),
        request_delay_seconds=float(sync.get("request_delay_seconds", 0.5)),
        activity_page_size=int(sync.get("activity_page_size", 100)),
        historical_start_date=(
            date.fromisoformat(str(sync["historical_start_date"]))
            if sync.get("historical_start_date")
            else None
        ),
        store_json=bool(raw.get("store_json", True)),
        store_fit=bool(raw.get("store_fit", True)),
    )
