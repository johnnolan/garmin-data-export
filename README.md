# Garmin local sync

> VIBECODE ALERT

A small, read-only Python application that archives Garmin Connect data to immutable raw files and
loads both summary and detailed time-series data into SQLite. It is intended to produce a dependable
local dataset for later analysis; it does not provide analysis, recommendations, a server, or a UI.

```text
Garmin Connect (read only)
        ↓
raw JSON + original ZIP/FIT (authoritative archive)
        ↓
FIT and health-data normalisation
        ↓
data/garmin.db (query layer)
```

Garmin Connect is accessed through the unofficial community-maintained `garminconnect` package.
Garmin can change private endpoints without notice. A library update or re-authentication may
occasionally be needed.

## Install on Debian

Prerequisites are Python 3.12 or newer, its `venv` module, Git, and normal build tooling:

```bash
sudo apt update
sudo apt install git python3 python3-venv build-essential

git clone <YOUR-REPOSITORY-URL> garmin-backup
cd garmin-backup
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development and tests, use `python -m pip install -e '.[dev]'` instead.

Defaults work without a configuration file. To customise paths or request pacing:

```bash
cp config.example.yaml config.yaml
```

Relative paths in `config.yaml` are resolved relative to that file. The default token cache is
`~/.garminconnect`, outside the repository. Do not put passwords or tokens in `config.yaml`.

## Authenticate

Initial authentication is interactive and supports Garmin MFA:

```bash
python -m garmin_sync auth
```

The command prompts for email, password, and (when required) an MFA code. It passes them directly to
`garminconnect`; only the reusable OAuth token cache is persisted. A scheduled sync loads that cache
without prompting. Run `auth` again if Garmin revokes or expires the refresh token.

For a non-interactive terminal setup only, the auth command also recognises `GARMIN_EMAIL` and
`GARMIN_PASSWORD`. Avoid putting either value in shell history, cron, configuration, or this repository.

## Sync

Initial complete activity history and daily data back to the oldest activity:

```bash
python -m garmin_sync sync --all
```

Garmin has no single account-wide “first health-data date” endpoint. If health records predate the
oldest activity, set `sync.historical_start_date` in `config.yaml` before the full sync. Full imports
page through every activity and deliberately make sequential, paced requests, so they can take a long
time. They are safe to restart.

Normal seven-day refresh:

```bash
python -m garmin_sync sync --days 7
```

Date-range repair:

```bash
python -m garmin_sync sync --from 2026-01-01 --to 2026-06-30
```

`sync` exits 0 when all required work succeeds. Device/account-specific optional health endpoints that
are unavailable are logged as warnings and do not fail the run. Activity/listing, raw-storage, or FIT
ingestion failures produce a partial run and exit 1 after continuing with other safe items.

Inspect local state:

```bash
python -m garmin_sync status
```

Recreate derived SQLite data solely from the raw archive, without contacting Garmin:

```bash
python -m garmin_sync rebuild
```

## Stored data

The raw archive is the local source of truth:

```text
data/raw/activities/YYYY/ACTIVITY_ID/activity.json
data/raw/activities/YYYY/ACTIVITY_ID/activity.zip
data/raw/activities/YYYY/ACTIVITY_ID/activity.fit
data/raw/daily/YYYY/MM/YYYY-MM-DD/<source>.json
```

Original Garmin activity downloads are retained as ZIP when supplied; the contained FIT is extracted
without modifying it. If Garmin returns changed JSON for an existing deterministic path, the original
file remains untouched and a content-hash-suffixed variant is added.

`data/garmin.db` contains:

- activity summaries plus complete Garmin JSON;
- every FIT session, lap, record, and event;
- otherwise-unmapped FIT messages (including file/device/sport/developer metadata) as JSON;
- daily summaries and complete daily API payloads;
- heart-rate, stress, Body Battery, sleep-stage, and HRV samples when Garmin supplies them;
- flattened training-readiness/status, VO2 max, race prediction, endurance, and hill metrics.

Common FIT fields—timestamps, GPS, altitude, heart rate, speed, cadence, power, temperature, running
dynamics, and more—are nullable columns in `activity_records`; every decoded field also remains in
`raw_json`. FIT rows are replaced per activity in one transaction using bulk inserts, making repeated
imports idempotent.

The sync attempts these daily sources independently: stats, heart rate, sleep, stress, HRV, Body
Battery, training readiness, training status/load, max metrics/VO2 max, race predictions, endurance
score, hill score, respiration, and SpO2. It intentionally does not mirror unrelated Garmin endpoints
such as social data, goals, challenges, golf, gear management, workouts, or hydration writes. Some
metrics exist only on supported devices, only for recent dates, or only for accounts where Garmin has
generated them; their absence is normal.

## Cron

Create the log directory if it does not already exist, then adapt both placeholder paths:

```bash
mkdir -p /home/USER/path/to/garmin-backup/logs
```

Example crontab entry, every four hours:

```cron
0 */4 * * * cd /home/USER/path/to/garmin-backup && /home/USER/path/to/garmin-backup/.venv/bin/python -m garmin_sync sync --days 7 >> /home/USER/path/to/garmin-backup/logs/garmin-sync.log 2>&1
```

The command does not depend on an activated shell environment or graphical session. Cron is not
installed or modified by this project.

## Backups and security

`data/`, `logs/`, local configuration, virtual environments, and token files are Git-ignored. Back up
`data/raw/` first: SQLite can be rebuilt from it. Backing up `data/garmin.db` is also useful for fast
recovery. Treat the external token directory as a secret, keep its permissions restricted, and back it
up only to encrypted storage. Never commit it.

SQLite uses foreign keys, WAL journaling, parameterised SQL, uniqueness constraints, and a schema
version table. When copying a live database, use SQLite's backup mechanism or stop the sync first so
the database and WAL are consistent.

## Development checks

Tests use mocked Garmin responses and never need credentials or network access:

```bash
source .venv/bin/activate
pytest
ruff check .
ruff format --check .
```

