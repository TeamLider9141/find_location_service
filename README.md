# Find Location

## What This Is

A Telegram bot holding a shared database of roadside places, contributed by the drivers
who use it. There is no third-party map data: a place exists in this bot because a driver
added it.

## Features

- Add a place: name, category, coordinates (Telegram location, map link or a lat/lon pair),
  and an optional note
- Duplicate warning when a similar name already exists within 200 m
- Search by name across Latin and Cyrillic spellings
- Browse by category
- Find places near your current location, sorted by distance
- Manage the places you contributed — change category, delete
- Per-user settings for search radius and result count, kept across restarts
- Admin panel — statistics, user list, per-user detail, top searches, moderation
  delete, broadcast. Reached with `/admin` or the 🛠 button, which only appears in
  the menu of an id listed in `ADMIN_IDS`
- Per-driver rate limit: bursts of five messages pass, anything faster is dropped
  with one warning
- Every id in `ADMIN_IDS` is messaged when the bot starts, so a restart is not silent

Six categories: restaurant, cafe, fuel, hotel, parking, car service.

## Architecture

- `app/domain` — entities, value objects, repository protocol
- `app/application` — use cases, name normalization
- `app/infrastructure` — SQLite repository, in-memory repository for tests
- `app/presentation/telegram` — handlers, keyboards, formatters, FSM states

Reads are global; writes are author-scoped. Anyone can look up any place, but only the
driver who added it can change or delete it. Admins listed in `ADMIN_IDS` are the exception:
they can delete any place, and they are the only ones who can open `/admin`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in TELEGRAM_BOT_TOKEN
```

Settings are read from `.env`; environment variables override it when both are present.

| Variable | Meaning |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather. Required. |
| `DATABASE_PATH` | SQLite file. Defaults to `data/find_location.sqlite3`. |
| `ADMIN_IDS` | Comma separated Telegram user ids allowed into `/admin`. Empty means nobody. |

## Run

```bash
python -m app.main
```

## Run Tests

```bash
python -m pytest -q
```
