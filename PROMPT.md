Build V1 of the Garmin local data-sync project described in `AGENTS.md`.

Start by reading `AGENTS.md` completely and treating it as the authoritative project specification.

Before implementing Garmin-specific calls, inspect the current documentation/source/examples for the installed/current `garminconnect` Python package. Do not invent method names or depend on old examples when the current API differs.

## Goal

I want a small Python application running on Debian that periodically synchronises my Garmin Connect data into:

1. Immutable raw JSON/FIT files.
2. A local SQLite database containing useful analysis-friendly summary data.

The resulting dataset will later be analysed by Codex, but analysis is explicitly out of scope for this task.

## Primary use cases

After installation and initial authentication I want these workflows:

```bash
# establish/re-establish Garmin authentication
python -m garmin_sync auth

# normal scheduled sync
python -m garmin_sync sync --days 7

# initial complete historical bootstrap
python -m garmin_sync sync --all

# repair/import a specific period
python -m garmin_sync sync --from 2026-01-01 --to 2026-06-30

# inspect local sync state
python -m garmin_sync status
```

The normal sync command will eventually be executed from cron.

## Important behaviour

The sync must be idempotent.

Running:

```bash
python -m garmin_sync sync --days 7
```

multiple times must not create duplicates.

Historical importing must also be safely restartable.

Garmin activity IDs should be treated as stable unique identifiers.

Persist enough raw source information that we can expand the SQLite schema later without redownloading everything.

For activities, archive both Garmin's activity JSON/details and the original FIT/original activity download wherever Garmin provides it.

For daily wellness/training data, archive the useful Garmin API responses as JSON.

Do not parse every FIT data point into SQLite yet.

## Initial Garmin data scope

Prioritise information useful for future endurance/trail-running analysis.

### Activities

Retrieve all activity types rather than filtering only running.

For each activity retrieve/store the high-level metadata required by `AGENTS.md`.

Also preserve the full raw activity JSON and original activity file.

### Daily information

Where the current Garmin library/account supports it, attempt to retrieve useful daily data including:

- daily stats
- heart rate
- sleep
- stress
- HRV
- Body Battery
- training readiness
- training status/load information
- VO2 max
- other directly relevant training/recovery summary information that is straightforward to obtain

Do not turn this into a project to mirror all 130+ Garmin endpoints.

If some metrics are unavailable historically or unsupported, handle that gracefully.

Raw JSON should allow us to retain fields we do not yet map into SQLite.

## Rate limiting/resilience

Be polite to Garmin.

Avoid high concurrency and aggressive request rates.

Historical imports may take a long time and that is acceptable.

Add a configurable small delay where appropriate.

Handle transient API/network errors sensibly.

A failure retrieving one optional metric should not destroy the whole import.

Provide clear logs and a final summary.

## Credentials

Use Garmin's supported token-store mechanism from the current `garminconnect` library.

Initial authentication may be interactive and may request MFA.

Scheduled sync must reuse persisted tokens and should not require credentials or MFA during normal operation unless Garmin invalidates the session.

Do not save passwords in this repository.

Do not log tokens, passwords or other secrets.

## Database

Use SQLite directly unless a very small dependency materially improves correctness.

Do not introduce PostgreSQL or an ORM unless there is an unusually compelling reason.

Create a schema version/migration mechanism now, even if it is simple.

Enable sensible SQLite options such as foreign keys.

Consider WAL mode if appropriate, but keep the implementation simple.

Use transactions correctly.

## Implementation quality

Use:

- type hints
- clear boundaries between Garmin access, raw persistence and database persistence
- useful exception handling
- Python logging
- pathlib
- parameterised SQL
- UTC-aware timestamps where appropriate

Avoid:

- unnecessary dependency injection frameworks
- repository/service abstractions with no practical benefit
- premature generic interfaces
- huge classes
- secrets in code
- broad catch-all exception handling that hides failures

## Tests

Create meaningful pytest tests using mocked Garmin responses.

Do not make tests depend on internet connectivity or my Garmin account.

Run the complete test suite when finished.

Also run formatting/linting if configured.

## README

Produce a practical README that I can follow from a fresh Debian shell.

It should include exact commands for:

```bash
git clone ...
cd ...
python3 -m venv .venv
source .venv/bin/activate
pip install ...
```

then authentication, first historical import and normal scheduled syncing.

Include an example cron job running every four hours with `--days 7`.

Make the example paths obvious placeholders rather than assuming my username.

## Cron/logging

Provide a `logs/` directory pattern and ensure log files/data/auth tokens are appropriately excluded from Git.

The Python process must return:

- exit code 0 for successful syncs, including optional Garmin metrics that simply are not available
- non-zero for a materially failed sync

## Work approach

Do not just scaffold the repository.

Implement a working end-to-end V1.

As you work:

1. Inspect `AGENTS.md`.
2. Research/inspect the current `garminconnect` package API.
3. Create the project structure.
4. Implement authentication.
5. Implement SQLite/schema management.
6. Implement raw storage.
7. Implement activity syncing/downloads.
8. Implement daily health/training syncing.
9. Implement the CLI.
10. Add tests.
11. Write the README.
12. Run tests/linting.
13. Review the implementation against every requirement in `AGENTS.md`.
14. Fix anything obvious before finishing.

When complete, give me:

- a concise summary of the architecture
- files created
- commands to install it
- command to authenticate
- command for my initial full-history import
- command for a normal 7-day sync
- suggested cron entry
- any Garmin data types you deliberately did not implement and why
- any assumptions or limitations discovered in the current `garminconnect` API
- results of tests/linting

Do not add an MCP server, Docker, analysis code or dashboard.