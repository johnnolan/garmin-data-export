from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any


class RawStore:
    """Content-preserving raw store: existing bytes are never changed."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.activities = root / "activities"
        self.daily = root / "daily"
        self.metadata = root / "metadata"
        for directory in (self.activities, self.daily, self.metadata):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_immutable(path: Path, content: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
            return path
        if path.read_bytes() == content:
            return path
        digest = hashlib.sha256(content).hexdigest()[:12]
        variant = path.with_name(f"{path.stem}-{digest}{path.suffix}")
        if not variant.exists():
            variant.write_bytes(content)
        elif variant.read_bytes() != content:
            raise RuntimeError(f"hash collision while storing {path}")
        return variant

    def store_json(self, path: Path, value: Any) -> Path:
        encoded = (json.dumps(value, indent=2, sort_keys=True, default=str) + "\n").encode()
        return self._write_immutable(path, encoded)

    def activity_directory(self, activity_id: str, year: int) -> Path:
        return self.activities / str(year) / str(activity_id)

    def store_activity_json(self, activity_id: str, year: int, value: Any) -> Path:
        return self.store_json(self.activity_directory(activity_id, year) / "activity.json", value)

    def store_activity_original(
        self, activity_id: str, year: int, content: bytes
    ) -> tuple[Path, Path | None]:
        directory = self.activity_directory(activity_id, year)
        if zipfile.is_zipfile(BytesIO(content)):
            original = self._write_immutable(directory / "activity.zip", content)
            fit_path = None
            with zipfile.ZipFile(BytesIO(content)) as archive:
                fits = sorted(name for name in archive.namelist() if name.lower().endswith(".fit"))
                if fits:
                    fit_path = self._write_immutable(
                        directory / "activity.fit", archive.read(fits[0])
                    )
            return original, fit_path
        fit_path = self._write_immutable(directory / "activity.fit", content)
        return fit_path, fit_path

    def daily_path(self, day: date, source: str) -> Path:
        return self.daily / f"{day:%Y}" / f"{day:%m}" / day.isoformat() / f"{source}.json"

    def store_daily(self, day: date, source: str, value: Any) -> Path:
        return self.store_json(self.daily_path(day, source), value)
