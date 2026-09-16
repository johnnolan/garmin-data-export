import pytest

from garmin_sync.cli import parser


def test_cli_rejects_non_positive_days():
    with pytest.raises(SystemExit):
        parser().parse_args(["sync", "--days", "0"])


def test_cli_modes_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        parser().parse_args(["sync", "--all", "--days", "7"])
