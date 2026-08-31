# Find Location

## What This Is

A Telegram bot holding a shared database of roadside places, contributed by the drivers
who use it. There is no third-party map data: a place exists in this bot because a driver
added it.

## Features

- Add a place: name, category, coordinates (Telegram location, map link or a lat/lon pair),
  and an optional note. Adding is gated: the first attempt sends an approval request to the
  admins, and the driver can add only after an admin allows it. Searching needs no approval.
- Duplicate warning when a similar name already exists within 200 m
- Search by name across Latin and Cyrillic spellings
- Browse by category — each button carries its place count; empty categories
  keep a plain label
- Tapping "nearby" first sends an overview sketch — every place in the
  database as dots on one auto-fitted static map — so the driver knows what
  there is before sharing their location. Needs the Maps Static API enabled
  on the Google key; without it the plain prompt goes out
- Find places near your current location, sorted by road distance — the nearest
  place by air is not always the nearest by road. Routing asks Google's Routes
  API first when a key is configured, then OSRM, and falls back to labelled
  straight-line distance when neither answers. Every result also carries a
  Yandex route link: the navigator's own route, one tap away
- Manage the places you contributed — change category, delete
- Per-user settings for search radius and result count, kept across restarts
- Admin panel — statistics, user list, per-user detail with a map link for every
  place they added, top searches, moderation delete, broadcast, add-permission
  approve/revoke, and a location browser: pick a category, see its places
  grouped by the driver who added them, with map links. Reached with `/admin`
  or the 🛠 button
- Two admin rungs: `ADMIN_IDS` may look at everything and manage add permissions;
  `SUPER_ADMIN_IDS` may additionally delete places and broadcast. The panel looks
  the same on both rungs — a super-only button refuses the tap with an alert
- Per-driver rate limit: bursts of five messages pass, anything faster is dropped
  with one warning
- Both admin rungs are messaged when a new user first opens the bot and when
  somebody asks for permission to add places; the startup notice goes to super
  admins only — restarts are routine and the ordinary rung cannot act on them

Eight categories: restaurant, cafe, fuel, hotel, parking, car service, mosque, and
`other` as a fallback — a place filed under a category it does not belong to is worse
than one filed under none.

## Architecture

- `app/domain` — entities, value objects, repository protocol
- `app/application` — use cases, name normalization
- `app/infrastructure` — SQLite repository, in-memory repository for tests
- `app/presentation/telegram` — handlers, keyboards, formatters, FSM states

Reads are global; writes are author-scoped. Anyone can look up any place, but only the
driver who added it can change or delete it. Super admins are the exception: they can
delete any place. Both admin rungs can open `/admin` and manage add permissions.

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
| `ADMIN_IDS` | Comma separated ids of ordinary admins: view the panel, approve and revoke add permissions. |
| `SUPER_ADMIN_IDS` | Comma separated ids of super admins: everything above, plus delete and broadcast. |
| `OSRM_BASE_URL` | OSRM server for road distances in the nearby search. Defaults to the public demo server; blank disables routing. |
| `GOOGLE_MAPS_API_KEY` | Optional Google Routes API key. When set, Google answers first and OSRM becomes the fallback. |
| `BACKUP_CHECK_INTERVAL_SECONDS` | How often the bot checks whether the database changed and mails it to the supers. Defaults to 86400 (daily), must be above 0. |
| `THROTTLE_BURST` | Messages a driver may send back to back. Defaults to 5, minimum 1. |
| `THROTTLE_REFILL_PER_SECOND` | Messages a second a driver earns back. Defaults to 1.0, must be above 0. |
| `THROTTLE_WARNING_SECONDS` | Seconds between two throttle replies. Defaults to 10; 0 answers every dropped message. |
| `THROTTLE_IDLE_SECONDS` | Seconds of silence before a driver is dropped from memory. Defaults to 300, must be above 0. |
| `THROTTLE_PRUNE_INTERVAL_SECONDS` | How often that cleanup sweep runs. Defaults to 60. |

A value that is unreadable or out of range is ignored and the default used instead — a
mistyped throttle must not be a way to lock the bot shut.

`scripts/env_cheklovlar.sh` writes the throttle block into an existing `.env`, with the
notes in Uzbek. It is safe to run twice; it replaces the block rather than appending to it.

The bot carries its own backup: every 24 hours it snapshots the database through
SQLite's backup API and, only when the file changed since the last send, mails the copy
to every id in `SUPER_ADMIN_IDS` as a Telegram document. No cron entry is needed — if a
`backup_bazani.sh` line is still in the server's crontab from before, remove it with
`crontab -e`, or the supers will keep receiving hourly copies alongside the daily one.
Every place deletion is also journalled in the `deletion_log` table — the 🧾 button in
the admin panel (super admins only) lists who deleted what, from where, and when.

## Run

```bash
python -m app.main
```

## Run Tests

```bash
python -m pytest -q
```
