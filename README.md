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
- Per-user settings for search radius and result count

Six categories: restaurant, cafe, fuel, hotel, parking, car service.

## Architecture

- `app/domain` — entities, value objects, repository protocol
- `app/application` — use cases, name normalization
- `app/infrastructure` — SQLite repository, in-memory repository for tests
- `app/presentation/telegram` — handlers, keyboards, formatters, FSM states

Reads are global; writes are author-scoped. Anyone can look up any place, but only the
driver who added it can change or delete it.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in TELEGRAM_BOT_TOKEN
```

Settings are read from `.env`; environment variables override it when both are present.

## Run

```bash
python -m app.main
```

## Run Tests

```bash
python -m pytest -q
```
