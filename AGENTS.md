# Garmin Analysis Project

## Purpose

This repository maintains a local, read-only copy of my Garmin Connect training and health data.

The initial goal is data ingestion and storage only.

Future versions will use this dataset for:

- Trail-running analysis
- Zone 2 aerobic-efficiency analysis
- Long-term training trends
- Weekly training reviews
- Recovery and fatigue analysis
- Comparison of similar workouts

Keep V1 simple. Do not build an MCP server, web application, dashboard, API, background service, or AI analysis layer.

## Core architecture

Garmin Connect
    ↓
Python sync script
    ↓
Raw immutable files + SQLite
    ↓
Future analysis tools / Codex

## Technology

Use:

- Python 3.12+
- `garminconnect`
- SQLite
- Python standard library where practical
- `pathlib`
- `argparse` or Typer for CLI handling
- pytest for tests

Avoid unnecessary frameworks.

Do not use Docker for V1.

The application must run cleanly from a Python virtual environment on Debian Linux.

## Design principles

### Garmin is read-only

This project must never modify Garmin Connect data.

Do not:

- create workouts
- update activities
- delete activities
- modify health data
- upload anything to Garmin

Only use read/export operations.

### Raw data is immutable

Everything retrieved from Garmin should have a raw representation stored beneath:

`data/raw/`

Raw files must never subsequently be modified.

If the same source data is downloaded again it may either:

- be skipped when unchanged, or
- safely overwrite an identical raw file

Never transform raw files in place.

### SQLite is the query layer

The database:

`data/garmin.db`

contains normalised/indexed data intended for analysis.

The raw archive remains the authoritative locally stored source.

The database must be rebuildable from raw data wherever practical.

### Idempotency

Running the same sync multiple times must be safe.

Use Garmin identifiers and appropriate database unique constraints.

Do not create duplicate activities, daily records, samples, or metadata.

Use UPSERT behaviour where data may legitimately change after initial ingestion.

### Incremental sync

Normal scheduled operation should re-fetch a configurable number of recent days.

Example:

`python -m garmin_sync sync --days 7`

Re-fetching recent days protects against:

- missed scheduled executions
- activities uploaded late
- Garmin recalculating metrics
- delayed health information

### Historical bootstrap

Support importing complete available Garmin history.

Example:

`python -m garmin_sync sync --all`

This must be restartable.

If a large historical sync fails halfway through, rerunning it should continue safely without corrupting or duplicating data.

Where Garmin APIs require pagination, implement pagination correctly.

Be conservative with Garmin request rates.

### Authentication

Use the authentication/token functionality provided by the maintained `garminconnect` library.

Prefer cached Garmin authentication tokens for unattended scheduled runs.

Never store Garmin usernames, passwords, MFA codes, OAuth tokens, or secrets in:

- source files
- SQLite
- configuration committed to Git
- logs

Support initial interactive authentication separately from unattended syncing.

Document how authentication is initialised.

Ensure relevant credential/token paths are excluded via `.gitignore`.

### Logging and errors

Output useful structured human-readable logs.

At minimum report:

- sync start
- sync mode/date range
- authentication status without secrets
- activities discovered
- activities downloaded
- activities skipped
- daily records processed
- errors
- final summary
- elapsed time

Exit non-zero when the sync genuinely fails so cron can detect failure.

One failed activity should not necessarily terminate an entire historical import.

Record/report failed items and continue where safe.

## Repository layout

Aim for approximately:

```text
.
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── config.example.yaml
├── src/
│   └── garmin_sync/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── auth.py
│       ├── client.py
│       ├── sync.py
│       ├── database.py
│       ├── raw_store.py
│       └── models.py
├── tests/
├── data/
│   ├── raw/
│   │   ├── activities/
│   │   ├── daily/
│   │   └── metadata/
│   └── garmin.db
└── reports/
```

The exact internal module split may be adjusted if there is a clear reason.

Generated `data/` content must not be committed to Git.

Keep placeholder `.gitkeep` files if useful.

## Raw activity storage

For each activity preserve:

1. Garmin activity metadata/details as JSON.
2. The original downloadable activity file, preferably FIT when Garmin supplies it.

Use deterministic filenames containing the Garmin activity ID.

Example:

```text
data/raw/activities/2026/123456789/
├── activity.json
└── activity.fit
```

If Garmin supplies a ZIP containing the original activity, preserving that original ZIP is acceptable.

Do not unnecessarily convert FIT into GPX or TCX.

FIT should be preferred because future analysis may require high-resolution data including:

- timestamp
- heart rate
- speed
- altitude
- cadence
- GPS
- temperature
- power where available

Parsing every FIT sample into SQLite is NOT required for V1.

Keep the original FIT file so this can be done later.

## Raw daily data

Store useful health/training responses as JSON grouped by date.

Example:

```text
data/raw/daily/2026/09/2026-09-15/
├── stats.json
├── heart_rate.json
├── sleep.json
├── stress.json
├── hrv.json
├── body_battery.json
├── training_readiness.json
└── training_status.json
```

Only create files for data actually available from Garmin.

Do not fail the complete daily sync because one metric is unavailable for a date/device/account.

## SQLite

Create migrations or a simple versioned schema mechanism from the beginning.

At minimum create tables representing:

### sync_runs

Track each execution.

Suggested fields:

- id
- started_at
- completed_at
- mode
- requested_start_date
- requested_end_date
- status
- activities_found
- activities_downloaded
- errors

### activities

Store useful high-level activity fields such as:

- garmin_activity_id
- name
- activity_type
- sport_type
- start_time_local
- start_time_utc if available
- distance_m
- duration_seconds
- moving_duration_seconds
- elapsed_duration_seconds
- elevation_gain_m
- elevation_loss_m
- average_speed
- max_speed
- average_hr
- max_hr
- average_cadence
- calories
- training_effect
- aerobic_training_effect
- anaerobic_training_effect
- activity_training_load
- vo2max where activity-specific and available
- raw_json_path
- fit_path
- created_at
- updated_at

Do not invent values when Garmin does not provide them.

Keep original Garmin JSON so schema additions can be backfilled later.

### daily_summary

Store analysis-friendly high-level daily information when available.

Potential fields include:

- date
- resting_hr
- average_hr
- max_hr
- steps
- calories
- sleep_seconds
- sleep_score
- hrv_status
- hrv_average
- stress_average
- body_battery_high
- body_battery_low
- training_readiness
- training_status
- vo2max
- raw data path/reference
- updated_at

Do not force unavailable metrics into inappropriate defaults.

NULL is preferable to guessed data.

Avoid over-normalising Garmin's entire API in V1.

Raw JSON exists specifically so future schema changes remain possible.

## Configuration

Configuration should contain non-secret settings only.

Example options:

```yaml
data_directory: ./data
database: ./data/garmin.db

sync:
  default_days: 7
  request_delay_seconds: 0.5

raw:
  store_json: true
  store_fit: true
```

Reasonable defaults should mean configuration is optional.

Secrets must not be stored here.

## CLI

Provide at minimum:

### Initialise authentication

A command or documented process for completing initial Garmin authentication/MFA and creating the reusable token cache.

For example:

`python -m garmin_sync auth`

The exact implementation should follow the current supported `garminconnect` authentication API.

### Recent sync

`python -m garmin_sync sync`

Uses configured/default recent-day window.

### Explicit recent window

`python -m garmin_sync sync --days 7`

### Complete historical sync

`python -m garmin_sync sync --all`

### Explicit date range

Useful for repairing/importing specific periods:

`python -m garmin_sync sync --from 2026-01-01 --to 2026-03-31`

If straightforward, also support:

`python -m garmin_sync status`

showing things such as:

- last successful sync
- newest activity
- oldest activity
- activity count
- daily-record range

## Cron compatibility

The command must work unattended from cron after authentication has been initialised.

Avoid depending on:

- current interactive shell configuration
- current working directory
- user input during normal sync
- graphical environment

Document an example such as:

```cron
0 */4 * * * cd /home/USER/garmin-analysis && /home/USER/garmin-analysis/.venv/bin/python -m garmin_sync sync --days 7 >> /home/USER/garmin-analysis/logs/garmin-sync.log 2>&1
```

Do not install the cron entry automatically.

## Testing

Unit tests should not make real Garmin API calls.

Abstract/wrap Garmin access enough that API responses can be mocked.

Tests should cover at least:

- database creation
- activity UPSERT/idempotency
- recent-date calculation
- historical pagination logic
- raw file paths
- rerunning an import
- partial failures
- CLI argument validation

Do not require my real Garmin credentials for automated tests.

## Documentation

README.md must explain:

1. What the project does.
2. Architecture.
3. Debian prerequisites.
4. Creating `.venv`.
5. Installing dependencies.
6. Initial Garmin authentication.
7. Running a 7-day sync.
8. Running a complete history import.
9. Running a date-range repair.
10. Database/raw file locations.
11. Example cron configuration.
12. Backup considerations.
13. Garmin Connect API caveat.

Clearly state that Garmin Connect is being accessed through an unofficial community API and could change.

## Scope discipline

Do not implement the following in V1:

- MCP server
- REST API
- web UI
- charts
- dashboards
- LLM integration
- training recommendations
- weekly reports
- automatic Git commits of data
- Docker
- cloud services

The purpose of V1 is to create a dependable Garmin → local archive → SQLite pipeline.

Prefer simple and maintainable code over abstraction for abstraction's sake.

## Complete SQLite ingestion

V1 MUST import detailed Garmin data into SQLite rather than keeping SQLite as a summary-only layer.

The purpose is to allow Codex to query and analyse the complete local Garmin dataset immediately after the initial historical sync.

Raw FIT and JSON files must still be retained as immutable source/archive data.

The architecture is therefore:

```text
Garmin Connect
    ↓
Raw FIT / JSON
    ↓
Decode / normalise
    ↓
SQLite
    ↓
Codex
```

The SQLite database should contain both:

1. Analysis-friendly normalised columns for common metrics.
2. Raw decoded JSON for fields that are uncommon, device-specific, or not yet explicitly modelled.

Do not discard Garmin/FIT fields simply because they are not currently required.

## FIT ingestion

Download the original activity file from Garmin wherever available.

Prefer FIT when supplied.

Use a maintained Python FIT decoder such as `fitdecode`, or another current implementation if inspection of available libraries identifies a clearly better choice.

Parse FIT data during the sync process.

At minimum ingest the following FIT message types where present:

- file_id
- activity
- session
- lap
- record
- event
- device_info
- sport
- developer_data_id
- field_description

Other message types should either:

- be mapped into an appropriate generic FIT messages table, or
- have their complete decoded representation retained as JSON.

Do not silently discard unknown FIT message types.

## activities

Store activity-level metadata including:

- Garmin activity ID
- name
- type
- sport/sub-sport
- local start time
- UTC start time where available
- distance
- elapsed duration
- moving duration
- elevation gain
- elevation loss
- average speed
- maximum speed
- average heart rate
- maximum heart rate
- average cadence
- calories
- aerobic training effect
- anaerobic training effect
- training load
- VO2 max where applicable
- raw Garmin JSON
- raw file path
- timestamps representing local DB creation/update

Use Garmin activity ID as the stable unique key.

## activity_sessions

Store all FIT session messages.

Include common fields as columns where practical and retain the full decoded FIT message in `raw_json`.

## activity_laps

Store all FIT lap messages.

Suggested columns include:

- activity_id
- session index
- lap index
- start_time
- end_time
- elapsed_time_seconds
- timer_time_seconds
- distance_m
- avg_speed_mps
- max_speed_mps
- avg_hr
- max_hr
- avg_cadence
- ascent_m
- descent_m
- calories
- raw_json

Use appropriate uniqueness constraints so repeated ingestion is idempotent.

## activity_records

Store the time-series `record` messages from FIT.

These are essential and MUST be imported into SQLite.

Suggested columns include where available:

- activity_id
- timestamp
- sequence number
- latitude
- longitude
- altitude_m
- enhanced_altitude_m
- heart_rate
- cadence
- fractional_cadence
- speed_mps
- enhanced_speed_mps
- distance_m
- power_w
- temperature_c
- grade
- vertical_speed
- vertical_oscillation
- ground_contact_time
- ground_contact_balance
- stance_time
- stance_time_balance
- step_length
- respiration_rate
- performance_condition
- accumulated_power
- calories
- raw_json

Do not invent absent data.

Columns should be nullable.

Preserve any additional fields in `raw_json`.

Index at least:

- activity_id
- timestamp
- `(activity_id, timestamp)`

Activity streams may contain thousands of rows, so use bulk inserts and transactions rather than issuing individual commits.

## activity_events

Store FIT events such as:

- timer starts/stops
- pauses
- resume events
- course points where relevant
- other recorded FIT events

Retain the complete message as JSON.

## FIT generic messages

Create a table capable of storing any decoded FIT message that is not explicitly normalised.

For example:

```text
fit_messages

id
activity_id
message_type
timestamp
message_index
raw_json
```

This exists to prevent loss of FIT information from device-specific or future message types.

## Daily/time-series Garmin data

Do not only store daily summary values.

When Garmin exposes intra-day/time-series data, store that data in SQLite as well.

Where available, create suitable tables for:

### heart_rate_samples

Fields such as:

- timestamp
- heart_rate
- source/date
- raw_json

### stress_samples

Fields such as:

- timestamp
- stress_level
- raw_json

### body_battery_samples

Fields such as:

- timestamp
- body_battery
- event_type/source where available
- raw_json

### sleep

Store both sleep summaries and available sleep stages/events.

Relevant data may include:

- sleep start/end
- deep sleep duration
- light sleep duration
- REM duration
- awake duration
- sleep score
- sleep stages
- respiration
- overnight HR
- HRV-related information

Keep raw source JSON.

### hrv

Store available daily and/or time-series HRV information.

### training_metrics

Store available training/recovery information including where Garmin exposes it:

- training readiness
- training status
- training load
- acute load
- load focus
- VO2 max
- recovery time
- race predictions
- endurance score
- hill score
- performance condition
- heat acclimation
- altitude acclimation

Do not assume every metric is available for every Garmin device/account.

Missing optional metrics must not fail the sync.

## Raw JSON storage

For Garmin API responses, use both:

- raw JSON files beneath `data/raw`
- JSON stored in appropriate SQLite rows where useful

The database should therefore remain useful even when Codex has access only to `garmin.db`.

## Database completeness

The guiding rule is:

> If Garmin supplied useful training, health, recovery or activity data, preserve it locally.

Prefer normalised/queryable columns for common metrics.

For everything else preserve the decoded/raw JSON.

The initial historical import should leave the user with a database that can be queried immediately without requiring a second enrichment/import process.

## Reprocessing

Provide a command to rebuild/reprocess SQL data from already downloaded raw files without contacting Garmin.

For example:

```bash
python -m garmin_sync rebuild
```

or:

```bash
python -m garmin_sync import-raw
```

This should:

- preserve raw source files
- recreate or update derived SQLite rows
- remain idempotent
- avoid Garmin API calls

This is important so future schema changes can be backfilled locally without redownloading history.

### Important change: complete SQL ingestion

Do NOT implement SQLite as a summary-only database.

The initial sync must produce a database suitable for detailed Codex analysis immediately.

For every downloaded activity:

1. Preserve the original activity file.
2. Preserve Garmin activity JSON.
3. Decode the FIT/original file where possible.
4. Insert activity summary data.
5. Insert sessions.
6. Insert laps.
7. Insert every time-series record/sample.
8. Insert FIT events.
9. Preserve otherwise-unmapped FIT messages and fields as JSON.

The key requirement is that detailed activity streams such as heart rate, speed, altitude, GPS, cadence and power are directly queryable from SQLite.

For Garmin health/recovery APIs, also store available time-series/intra-day data rather than only daily averages.

The database should support queries such as:

```sql
SELECT
    timestamp,
    heart_rate,
    speed_mps,
    altitude_m,
    cadence
FROM activity_records
WHERE activity_id = ?
ORDER BY timestamp;
```

and:

```sql
SELECT
    a.start_time_local,
    a.distance_m,
    a.average_hr,
    a.elevation_gain_m,
    COUNT(r.id) AS samples
FROM activities a
LEFT JOIN activity_records r
    ON r.activity_id = a.garmin_activity_id
WHERE a.activity_type LIKE '%running%'
GROUP BY a.garmin_activity_id
ORDER BY a.start_time_local DESC;
```

Use efficient batch insertion.

An activity may contain thousands of FIT records. Do not commit each sample individually.

Use transactions and `executemany()` or an equivalent efficient approach.

Create useful indexes for analytical querying, particularly:

- activity ID
- timestamps
- activity type
- activity start time
- daily metric dates

Retain raw JSON fields so device-specific metrics are not lost.

Also implement a local-only reprocessing command:

```bash
python -m garmin_sync rebuild
```

This must rebuild/repopulate SQLite from existing files beneath `data/raw/` without contacting Garmin.

This allows future database schema changes to be applied to historical data without another Garmin download.

The result of the initial:

```bash
python -m garmin_sync sync --all
```

should therefore be a complete local dataset ready for Codex to query immediately.
