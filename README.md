# Find Location

Provider-agnostic location search pipeline for a Telegram bot aimed at taxi and truck drivers in Russia.

Current stage:

- Python project skeleton
- configuration and logging helpers
- domain models for `Coordinates`, `Location`, `Place`, and `PlaceCategory`
- provider interfaces for geocoding, nearby places, and future routing
- OSM Nominatim geocoding provider
- Nominatim response mapper into normalized `Location`
- search-location use case
- Telegram handlers for search, selection, saved places, category updates, and delete confirmation
- SQLite-backed saved place repository behind a repository interface
- unit/provider tests plus an opt-in live Nominatim integration test

Not included yet:

- Overpass nearby places
- Redis cache
- PostgreSQL/PostGIS
- Yandex providers

## Run Tests

```bash
python -m pytest
```

Live OSM query test:

```bash
RUN_REAL_OSM=1 python -m pytest tests/integration
```

## Manual Query

```bash
python -m app.main "Домодедово аэропорт"
```

## Run Telegram Bot

```bash
python -m app.main --bot
```

Current bot flow:

- `/start` opens the reply keyboard menu
- `🔎 Manzil qidirish` is shown on the top row
- `➕ Manzil qo'shish` and `📍 Saqlangan manzillar` are shown below it
- `/cancel` is shown on the bottom row and resets the current process
- press `🔎 Manzil qidirish` and send an address/place name
- receive Nominatim search results as inline buttons
- select one result and receive coordinates plus a map link
- the selected result shows its original result number
- use inline category buttons to see nearby places within 5 km around the selected result
- use the realtime nearby option to choose a category and send your current Telegram Location
- press `➕ Manzil qo'shish` to send an address/place name, map link, Telegram Location, or Telegram Venue
- add the selected place to the database
- choose a category, then confirm saving
- press `📍 Saqlangan manzillar` to list categories first
- empty categories are shown with `(bo'sh)` in the inline category list
- select a category to list saved places inside that category
- change the saved place category later from inline buttons
- delete the saved place after inline confirmation

Saved places are currently stored in SQLite at `DATABASE_PATH`. The repository
is behind an interface, so this can be moved to PostgreSQL/PostGIS later without
changing Telegram handlers.

Settings are loaded from `.env` by default. Environment variables override
values from `.env` when both are present.

Required for the future Telegram bot:

```env
TELEGRAM_BOT_TOKEN=
```

Optional OSM settings:

```env
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
OVERPASS_BASE_URL=https://overpass-api.de/api
NOMINATIM_USER_AGENT=find-location-bot/0.1
DATABASE_PATH=data/find_location.sqlite3
```
