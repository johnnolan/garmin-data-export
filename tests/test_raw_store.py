import zipfile
from datetime import date
from io import BytesIO

from garmin_sync.raw_store import RawStore


def test_raw_paths_and_immutable_variants(tmp_path):
    store = RawStore(tmp_path / "raw")
    first = store.store_activity_json("123", 2026, {"version": 1})
    same = store.store_activity_json("123", 2026, {"version": 1})
    changed = store.store_activity_json("123", 2026, {"version": 2})
    assert first == same
    assert changed != first
    assert first.read_text().find('"version": 1') > 0
    assert changed.parent == tmp_path / "raw" / "activities" / "2026" / "123"
    assert (
        store.daily_path(date(2026, 9, 15), "sleep")
        .as_posix()
        .endswith("daily/2026/09/2026-09-15/sleep.json")
    )


def test_original_zip_and_contained_fit_are_both_preserved(tmp_path):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("123.fit", b"FIT payload")
    original, fit = RawStore(tmp_path / "raw").store_activity_original(
        "123", 2026, buffer.getvalue()
    )
    assert original.name == "activity.zip"
    assert fit is not None
    assert fit.read_bytes() == b"FIT payload"
