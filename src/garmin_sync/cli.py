from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from .auth import cached_client, interactive_login
from .client import GarminReader
from .config import load_config
from .database import Database
from .raw_store import RawStore
from .sync import Synchronizer, all_window, date_range, rebuild, recent_window


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}; expected YYYY-MM-DD") from error


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m garmin_sync")
    root.add_argument("--config", type=Path, help="configuration YAML (default: ./config.yaml)")
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="create or refresh the Garmin token cache")
    sync = commands.add_parser("sync", help="synchronise Garmin data")
    mode = sync.add_mutually_exclusive_group()
    mode.add_argument("--days", type=positive_int)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--from", dest="from_date", type=iso_date)
    sync.add_argument("--to", dest="to_date", type=iso_date)
    commands.add_parser("status", help="show local archive/database state")
    commands.add_parser("rebuild", help="rebuild SQLite only from data/raw")
    return root


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    configure_logging(arguments.verbose)
    try:
        config = load_config(arguments.config)
        if arguments.command == "auth":
            client = interactive_login(config.token_store)
            name = client.get_full_name()
            print(
                f"Authentication successful{f' for {name}' if name else ''}. Tokens: {config.token_store}"
            )
            return 0

        db = Database(config.database)
        try:
            db.migrate()
            raw = RawStore(config.data_directory / "raw")
            if arguments.command == "status":
                state = db.status()
                print(f"Database: {config.database}")
                print(f"Activities: {state['activity_count']}")
                print(
                    f"Activity range: {state['oldest_activity'] or '-'} to {state['newest_activity'] or '-'}"
                )
                print(
                    f"Daily range: {state['oldest_daily'] or '-'} to {state['newest_daily'] or '-'}"
                )
                print(f"Last successful sync: {state['last_successful_sync'] or '-'}")
                return 0
            if arguments.command == "rebuild":
                stats = rebuild(config, db, raw)
                print(
                    f"Rebuilt {stats.activities_found} activities and {stats.daily_records_processed} daily payloads"
                )
                if stats.errors:
                    for error in stats.errors:
                        logging.error("%s", error)
                    return 1
                return 0

            if arguments.to_date and not arguments.from_date:
                parser().error("--to requires --from")
            if arguments.from_date:
                window = date_range(arguments.from_date, arguments.to_date or date.today())
            elif arguments.all:
                window = all_window()
            else:
                window = recent_window(arguments.days or config.default_days)
            logging.info("authenticating with cached tokens at %s", config.token_store)
            api = cached_client(config.token_store)
            logging.info("authentication successful")
            reader = GarminReader(api, config.request_delay_seconds, config.activity_page_size)
            stats, status = Synchronizer(config, db, raw, reader).run(window)
            return 0 if status == "success" else 1
        finally:
            db.close()
    except KeyboardInterrupt:
        logging.error("interrupted")
        return 130
    except Exception as error:
        logging.error("%s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
