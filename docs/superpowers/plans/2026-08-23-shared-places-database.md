# Shared Community Places Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the OpenStreetMap-backed lookup with a shared, user-contributed places database: any driver adds a place (name, category, coordinates, optional note), and every other driver can find it by name, by category, or by distance from their current location.

**Architecture:** Clean architecture layers stay as they are — domain / application / infrastructure / presentation. The OSM provider package disappears entirely, and `SavedPlace` (a private per-user copy) becomes `Place` (the shared record itself). Reads are global; writes are author-scoped. Multi-step Telegram flows move from ad-hoc string modes to aiogram's built-in FSM.

**Tech Stack:** Python 3.10 (runtime; `pyproject.toml` declares `>=3.12` — see Task 26), aiogram 3.27, SQLite via stdlib `sqlite3`, pytest 8 with `asyncio_mode = "auto"`.

**Spec:** `docs/superpowers/specs/2026-08-23-shared-places-database-design.md`

---

## Conventions used throughout this plan

**Running tests.** Always from the repo root: `python -m pytest -q`. A single test:
`python -m pytest tests/unit/test_x.py::test_name -v`.

**Commit messages.** Conventional Commits: `type(scope): description`, imperative,
lowercase, no trailing period, subject ≤72 chars. Never add attribution trailers
(no `Co-Authored-By`, no "Generated with"). The body explains *why*, not *what*.

**Baseline.** Before Task 1, `python -m pytest -q` reports **82 passed, 1 skipped**. Tasks
1–13 only add files, so that number only grows. Tasks 14+ replace old code, and the
per-task expected counts are stated where they change.

**Async tests.** `asyncio_mode = "auto"` is set, so `async def test_...` needs no decorator.

---

# Phase 1 — Domain and repository

Nothing in this phase touches existing code. The old bot keeps working the whole time.

---

### Task 1: The `Place` entity

The current `app/domain/entities/place.py` holds the OSM search result type. It is only
imported by the OSM provider and its use case, both of which are deleted in Phase 5, so
overwriting it now is safe — but the old bot still imports it, so we keep the module
importable by giving it the new shape and fixing consumers in Phase 5. To avoid breaking
the suite mid-flight, create the new entity under a new name **first** and rename in
Phase 5.

**Files:**
- Create: `app/domain/entities/community_place.py`
- Test: `tests/unit/test_community_place.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


def test_place_carries_author_and_optional_note() -> None:
    place = Place(
        id=1,
        added_by_user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 8, 23, 12, 0, 0),
    )

    assert place.added_by_user_id == 42
    assert place.note == ""


def test_place_is_immutable() -> None:
    place = Place(
        id=1,
        added_by_user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 8, 23, 12, 0, 0),
    )

    try:
        place.name = "Лукойл"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Place must be frozen")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_community_place.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.entities.community_place'`

- [ ] **Step 3: Write minimal implementation**

`app/domain/entities/community_place.py`:

```python
from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


@dataclass(frozen=True)
class Place:
    """A place contributed by a driver and shared with every other driver.

    ``added_by_user_id`` is not an ownership fence for reading — anyone can look a
    place up. It only decides who may edit or delete it.
    """

    id: int
    added_by_user_id: int
    name: str
    category: PlaceCategory
    coordinates: Coordinates
    note: str
    created_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_community_place.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/domain/entities/community_place.py tests/unit/test_community_place.py
git commit -m "feat(domain): add shared Place entity"
```

---

### Task 2: Name normalization

Drivers type `gazprom`; the database holds `Газпром`. One normalized column makes both
find each other. This reuses the transliteration table already in
`app/application/query_normalization.py`, which is deleted in Phase 5.

**Files:**
- Create: `app/application/name_normalization.py`
- Test: `tests/unit/test_name_normalization.py`

- [ ] **Step 1: Write the failing test**

```python
from app.application.name_normalization import normalize_name


def test_normalize_lowercases_and_trims() -> None:
    assert normalize_name("  Газпром  ") == "газпром"


def test_normalize_transliterates_latin_to_cyrillic() -> None:
    assert normalize_name("Gazprom") == "газпром"


def test_latin_and_cyrillic_spellings_normalize_to_the_same_value() -> None:
    assert normalize_name("Lukoil") == normalize_name("Лукоил")


def test_normalize_handles_digraphs() -> None:
    assert normalize_name("Shell") == "шелл"


def test_normalize_collapses_inner_whitespace() -> None:
    assert normalize_name("Кафе   У   Дороги") == "кафе у дороги"


def test_normalize_of_empty_string_is_empty() -> None:
    assert normalize_name("   ") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_name_normalization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.application.name_normalization'`

- [ ] **Step 3: Write minimal implementation**

`app/application/name_normalization.py`:

```python
import re

_LATIN_RE = re.compile(r"[A-Za-z]")
_WHITESPACE_RE = re.compile(r"\s+")

_DIGRAPHS: dict[str, str] = {
    "sch": "щ",
    "shh": "щ",
    "yo": "ё",
    "yu": "ю",
    "ya": "я",
    "ye": "е",
    "zh": "ж",
    "kh": "х",
    "ts": "ц",
    "ch": "ч",
    "sh": "ш",
}

_LETTERS: dict[str, str] = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "ы",
    "z": "з",
}


def normalize_name(name: str) -> str:
    """Return the search key for a place name.

    Lowercases, collapses whitespace and transliterates Latin spellings into
    Cyrillic, so that "Gazprom" and "Газпром" share one key.
    """
    collapsed = _WHITESPACE_RE.sub(" ", name.strip()).lower()
    if not collapsed:
        return ""
    return _transliterate(collapsed)


def _transliterate(value: str) -> str:
    if _LATIN_RE.search(value) is None:
        return value

    output: list[str] = []
    index = 0
    while index < len(value):
        for size in (3, 2):
            chunk = value[index : index + size]
            if chunk in _DIGRAPHS:
                output.append(_DIGRAPHS[chunk])
                index += size
                break
        else:
            output.append(_LETTERS.get(value[index], value[index]))
            index += 1

    return "".join(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_name_normalization.py -v`
Expected: PASS (6 passed)

Note on `test_latin_and_cyrillic_spellings_normalize_to_the_same_value`: `"Lukoil"`
transliterates to `"лукоил"` and `"Лукоил"` is already `"лукоил"`, so they match. The
real-world spelling `"Лукойл"` normalizes to `"лукойл"` and does **not** match — the
table is a one-way approximation, not a reversible mapping. That is acceptable: `search`
uses substring matching (Task 6), so `"лукои"` still finds neither, but `"лукойл"` typed
in Cyrillic finds the Cyrillic record. This is a known limit, recorded in the spec's
out-of-scope list.

- [ ] **Step 5: Commit**

```bash
git add app/application/name_normalization.py tests/unit/test_name_normalization.py
git commit -m "feat(application): add place name normalization"

# Why: drivers type Latin, the database holds Cyrillic; one normalized key
# lets both spellings find the same record.
```

---

### Task 3: The `PlaceRepository` protocol

A Protocol has no behavior to test on its own, so this task has no test of its own — the
SQLite and in-memory implementations in Tasks 4–10 are what prove the contract. Keep the
file small and complete so both implementations can be written against it.

**Files:**
- Create: `app/domain/interfaces/community_places.py`

- [ ] **Step 1: Write the protocol**

`app/domain/interfaces/community_places.py`:

```python
from typing import Protocol

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates

DEFAULT_DUPLICATE_RADIUS_METERS = 200


class PlaceRepository(Protocol):
    def add(self, place: Place) -> Place:
        """Persist a place and return it with its database id and created_at."""

    def get(self, place_id: int) -> Place | None:
        """Return one place. Readable by anyone — no author filter."""

    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        """Return places matching a name fragment and/or a category.

        Both filters are optional. ``name`` matches as a normalized substring.
        """

    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        """Return places within the radius, nearest first."""

    def list_by_author(self, user_id: int) -> list[Place]:
        """Return every place this user contributed, newest first."""

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        """Return existing places with an overlapping name inside the radius."""

    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None:
        """Change a place the user contributed.

        ``None`` means "leave this field alone"; an empty string clears the note.
        Returns None when the place does not exist or belongs to someone else.
        """

    def delete(self, place_id: int, user_id: int) -> bool:
        """Delete a place the user contributed. False when not theirs."""
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from app.domain.interfaces.community_places import PlaceRepository; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/domain/interfaces/community_places.py
git commit -m "feat(domain): add PlaceRepository protocol"

# Why: reads are global but writes are author-scoped, so user_id appears on
# update/delete and deliberately not on get/search/nearby.
```

---

### Task 4: SQLite repository — schema, `add` and `get`

**Files:**
- Create: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

import pytest

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository


@pytest.fixture
def repository(tmp_path) -> SQLitePlaceRepository:
    return SQLitePlaceRepository(tmp_path / "places.sqlite3")


def make_place(
    name: str = "Газпром",
    category: PlaceCategory = PlaceCategory.FUEL,
    latitude: float = 55.75,
    longitude: float = 37.61,
    user_id: int = 42,
    note: str = "",
) -> Place:
    return Place(
        id=0,
        added_by_user_id=user_id,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        note=note,
        created_at=datetime(2026, 1, 1),
    )


def test_add_assigns_an_id(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place())

    assert stored.id > 0
    assert stored.name == "Газпром"


def test_add_stamps_created_at(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place())

    assert isinstance(stored.created_at, datetime)


def test_get_returns_the_place_for_any_user(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(user_id=42))

    found = repository.get(stored.id)

    assert found is not None
    assert found.added_by_user_id == 42
    assert found.coordinates.latitude == pytest.approx(55.75)


def test_get_returns_none_for_unknown_id(repository: SQLitePlaceRepository) -> None:
    assert repository.get(999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.database.sqlite_places'`

- [ ] **Step 3: Write minimal implementation**

`app/infrastructure/database/sqlite_places.py`:

```python
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from app.application.name_normalization import normalize_name
from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates

_COLUMNS = """
    id, added_by_user_id, name, category, latitude, longitude, note, created_at
"""


class SQLitePlaceRepository:
    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(self, place: Place) -> Place:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO places (
                    added_by_user_id, name, name_normalized, category,
                    latitude, longitude, note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    place.added_by_user_id,
                    place.name,
                    normalize_name(place.name),
                    place.category.value,
                    place.coordinates.latitude,
                    place.coordinates.longitude,
                    place.note,
                ),
            )
            connection.commit()
            place_id = int(cursor.lastrowid)

        stored = self.get(place_id)
        if stored is None:  # pragma: no cover - insert just succeeded
            raise RuntimeError("inserted place disappeared")
        return stored

    def get(self, place_id: int) -> Place | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM places WHERE id = ?",
                (place_id,),
            ).fetchone()

        return _map_row(row) if row is not None else None

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS places (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    added_by_user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    name_normalized TEXT NOT NULL,
                    category TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_category ON places(category)"
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_places_name_normalized
                ON places(name_normalized)
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_author ON places(added_by_user_id)"
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _map_row(row: Row) -> Place:
    return Place(
        id=int(row["id"]),
        added_by_user_id=int(row["added_by_user_id"]),
        name=str(row["name"]),
        category=PlaceCategory(str(row["category"])),
        coordinates=Coordinates(
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        ),
        note=str(row["note"]),
        created_at=_parse_timestamp(str(row["created_at"])),
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): add SQLite places table with add and get"

# Why: get() takes no user_id because the database is shared — every driver
# reads every contribution.
```

---

### Task 5: SQLite repository — `search` by category

**Files:**
- Modify: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sqlite_place_repository.py`:

```python
def test_search_by_category_returns_only_that_category(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", category=PlaceCategory.FUEL))
    repository.add(make_place(name="Придорожное", category=PlaceCategory.RESTAURANT))

    results = repository.search(category=PlaceCategory.FUEL)

    assert [place.name for place in results] == ["Газпром"]


def test_search_without_filters_returns_everything(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))
    repository.add(make_place(name="Лукойл"))

    assert len(repository.search()) == 2


def test_search_respects_limit(repository: SQLitePlaceRepository) -> None:
    for index in range(5):
        repository.add(make_place(name=f"Газпром {index}"))

    assert len(repository.search(limit=2)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -k search -v`
Expected: FAIL — `AttributeError: 'SQLitePlaceRepository' object has no attribute 'search'`

- [ ] **Step 3: Write minimal implementation**

Add to `SQLitePlaceRepository`, directly after `get`:

```python
    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        conditions: list[str] = []
        parameters: list[object] = []

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM places {where} ORDER BY name ASC LIMIT ?",
                parameters,
            ).fetchall()

        return [_map_row(row) for row in rows]
```

`name` is accepted but ignored until Task 6 — the signature is fixed by the protocol, so
declaring it now avoids changing the call sites twice.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): search places by category"
```

---

### Task 6: SQLite repository — `search` by name

**Files:**
- Modify: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sqlite_place_repository.py`:

```python
def test_search_by_name_matches_a_substring(repository: SQLitePlaceRepository) -> None:
    repository.add(make_place(name="Кафе У Дороги"))
    repository.add(make_place(name="Газпром"))

    results = repository.search(name="дороги")

    assert [place.name for place in results] == ["Кафе У Дороги"]


def test_search_by_latin_name_finds_a_cyrillic_record(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))

    results = repository.search(name="gazprom")

    assert [place.name for place in results] == ["Газпром"]


def test_search_by_name_and_category_applies_both(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", category=PlaceCategory.FUEL))
    repository.add(make_place(name="Газпром кафе", category=PlaceCategory.CAFE))

    results = repository.search(name="газпром", category=PlaceCategory.CAFE)

    assert [place.name for place in results] == ["Газпром кафе"]


def test_search_by_blank_name_is_treated_as_no_name_filter(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))

    assert len(repository.search(name="   ")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -k name -v`
Expected: FAIL — `test_search_by_name_matches_a_substring` returns both rows, so
`AssertionError: assert ['Кафе У Дороги', 'Газпром'] == ['Кафе У Дороги']`

- [ ] **Step 3: Write minimal implementation**

Replace the body of `search` with:

```python
    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        conditions: list[str] = []
        parameters: list[object] = []

        normalized_name = normalize_name(name) if name is not None else ""
        if normalized_name:
            conditions.append("name_normalized LIKE ?")
            parameters.append(f"%{_escape_like(normalized_name)}%")

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM places {where} ORDER BY name ASC LIMIT ?",
                parameters,
            ).fetchall()

        return [_map_row(row) for row in rows]
```

Add this module-level helper next to `_map_row`:

```python
def _escape_like(value: str) -> str:
    """Neutralize LIKE wildcards so a name containing % or _ still matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```

And make SQLite honor the escape character by changing the `LIKE ?` condition to:

```python
            conditions.append("name_normalized LIKE ? ESCAPE '\\'")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): search places by normalized name"

# Why: matching on name_normalized lets a driver type "gazprom" and reach a
# record stored as "Газпром". LIKE wildcards in the query are escaped so a
# name containing % cannot widen the match.
```

---

### Task 7: SQLite repository — `nearby`

Two stages: a bounding box in SQL (cheap, uses no trigonometry), then exact Haversine
distances in Python via the existing `Coordinates.distance_to`.

**Files:**
- Modify: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sqlite_place_repository.py`:

```python
def test_nearby_excludes_places_outside_the_radius(
    repository: SQLitePlaceRepository,
) -> None:
    # ~1.1 km north of the origin.
    repository.add(make_place(name="Близко", latitude=55.7600, longitude=37.6100))
    # ~11 km north of the origin.
    repository.add(make_place(name="Далеко", latitude=55.8500, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Близко"]


def test_nearby_sorts_by_distance(repository: SQLitePlaceRepository) -> None:
    repository.add(make_place(name="Дальше", latitude=55.7700, longitude=37.6100))
    repository.add(make_place(name="Ближе", latitude=55.7510, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_nearby_can_filter_by_category(repository: SQLitePlaceRepository) -> None:
    repository.add(
        make_place(name="Заправка", latitude=55.7510, category=PlaceCategory.FUEL)
    )
    repository.add(
        make_place(name="Кафе", latitude=55.7511, category=PlaceCategory.CAFE)
    )

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
        category=PlaceCategory.CAFE,
    )

    assert [place.name for place in results] == ["Кафе"]


def test_nearby_respects_limit(repository: SQLitePlaceRepository) -> None:
    for index in range(5):
        repository.add(make_place(name=f"Место {index}", latitude=55.7500 + index / 1000))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
        limit=2,
    )

    assert len(results) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -k nearby -v`
Expected: FAIL — `AttributeError: 'SQLitePlaceRepository' object has no attribute 'nearby'`

- [ ] **Step 3: Write minimal implementation**

Add to `SQLitePlaceRepository`, after `search`:

```python
    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        box = _bounding_box(coordinates, radius_meters)
        conditions = [
            "latitude BETWEEN ? AND ?",
            "longitude BETWEEN ? AND ?",
        ]
        parameters: list[object] = [
            box.min_latitude,
            box.max_latitude,
            box.min_longitude,
            box.max_longitude,
        ]

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category.value)

        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM places WHERE {' AND '.join(conditions)}",
                parameters,
            ).fetchall()

        within_radius = [
            (coordinates.distance_to(place.coordinates), place)
            for place in (_map_row(row) for row in rows)
        ]
        within_radius = [item for item in within_radius if item[0] <= radius_meters]
        within_radius.sort(key=lambda item: item[0])
        return [place for _, place in within_radius[:limit]]
```

Add these module-level helpers next to `_map_row`:

```python
@dataclass(frozen=True)
class _BoundingBox:
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float


def _bounding_box(coordinates: Coordinates, radius_meters: int) -> _BoundingBox:
    """A rectangle that contains the radius circle, with a small safety margin.

    This is a cheap prefilter — the exact Haversine check runs in Python
    afterwards — so the box may be too large but must never be too small.
    That is why it measures on the same sphere as ``Coordinates.distance_to``:
    a flat metres-per-degree constant comes out slightly narrower than Haversine
    measures and silently drops places that are genuinely inside the radius.

    The box does not wrap the antimeridian; a search centred near +/-180
    longitude is clipped rather than continued on the other side. That costs
    nothing for the drivers this bot serves.
    """
    angular_radius = radius_meters * _BOX_MARGIN / _EARTH_RADIUS_METERS
    latitude_delta = degrees(angular_radius)

    # Longitude degrees shrink towards the poles, so the same distance spans
    # more of them the further north you are. Close enough to a pole the circle
    # covers every longitude, which is what a sine of 1 or more means.
    longitude_sine = sin(angular_radius) / max(cos(radians(coordinates.latitude)), 1e-9)
    longitude_delta = (
        180.0 if longitude_sine >= 1 else degrees(asin(longitude_sine))
    )

    return _BoundingBox(
        min_latitude=max(coordinates.latitude - latitude_delta, -90.0),
        max_latitude=min(coordinates.latitude + latitude_delta, 90.0),
        min_longitude=max(coordinates.longitude - longitude_delta, -180.0),
        max_longitude=min(coordinates.longitude + longitude_delta, 180.0),
    )
```

Add to the top of the module:

```python
from dataclasses import dataclass
from math import asin, cos, degrees, radians, sin

_EARTH_RADIUS_METERS = 6_371_000
_BOX_MARGIN = 1.001
```

`_EARTH_RADIUS_METERS` must match the sphere `Coordinates.distance_to` uses. A flat
111_320 m per degree (the WGS84 figure) is 0.11% too large, which makes the box span
4994 m for a 5000 m radius and silently drop places the Haversine check would have
accepted. `_BOX_MARGIN` only absorbs floating-point noise at the boundary.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (18 passed)

Three of those 18 exist to stop the box from quietly doing all the work: one place
just inside the radius but outside a box built from a flat constant, one place inside
the box corner but outside the radius, and two places at an identical distance so the
`key=lambda item: item[0]` cannot be dropped without a `TypeError`.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): find places near coordinates"

# Why: SQLite has no trigonometry, so a bounding box narrows the rows before
# Haversine runs on the survivors. The places table has no lat/lon index, so
# that stage is a full scan — it cuts Python's work, not SQLite's.
```

---

### Task 8: SQLite repository — `list_by_author`

**Files:**
- Modify: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sqlite_place_repository.py`:

```python
def test_list_by_author_returns_only_that_users_places(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Моё", user_id=42))
    repository.add(make_place(name="Чужое", user_id=7))

    results = repository.list_by_author(42)

    assert [place.name for place in results] == ["Моё"]


def test_list_by_author_returns_newest_first(repository: SQLitePlaceRepository) -> None:
    first = repository.add(make_place(name="Первое", user_id=42))
    second = repository.add(make_place(name="Второе", user_id=42))

    results = repository.list_by_author(42)

    assert [place.id for place in results] == [second.id, first.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -k list_by_author -v`
Expected: FAIL — `AttributeError: 'SQLitePlaceRepository' object has no attribute 'list_by_author'`

- [ ] **Step 3: Write minimal implementation**

Add to `SQLitePlaceRepository`, after `nearby`:

```python
    def list_by_author(self, user_id: int) -> list[Place]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} FROM places
                WHERE added_by_user_id = ?
                ORDER BY id DESC
                """,
                (user_id,),
            ).fetchall()

        return [_map_row(row) for row in rows]
```

Ordering is by `id DESC` rather than `created_at DESC` because `CURRENT_TIMESTAMP` has
one-second resolution — two places added in the same second would tie, and the
autoincrement id never does.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (17 passed)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): list places by their author"
```

---

### Task 9: SQLite repository — `find_duplicates`

Two records are duplicates when their normalized names are equal or one contains the
other, **and** they sit within the radius. No fuzzy matching: it misses typos, but the
result is predictable and explainable to the driver.

**Files:**
- Modify: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sqlite_place_repository.py`:

```python
def test_find_duplicates_matches_same_name_within_radius(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром",
        coordinates=Coordinates(latitude=55.7501, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_duplicates_ignores_same_name_outside_radius(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром",
        # ~1.1 km away.
        coordinates=Coordinates(latitude=55.7600, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_find_duplicates_matches_a_containing_name(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром 24",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_duplicates_ignores_a_different_name_nearby(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Лукойл",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_find_duplicates_matches_across_alphabets(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Gazprom",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -k duplicates -v`
Expected: FAIL — `AttributeError: 'SQLitePlaceRepository' object has no attribute 'find_duplicates'`

- [ ] **Step 3: Write minimal implementation**

Add to `SQLitePlaceRepository`, after `list_by_author`:

```python
    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return []

        candidates = self.nearby(coordinates, radius_meters, limit=_DUPLICATE_SCAN_LIMIT)
        return [
            place
            for place in candidates
            if _names_overlap(normalized_name, normalize_name(place.name))
        ]
```

Add to the module-level helpers:

```python
_DUPLICATE_SCAN_LIMIT = 50


def _names_overlap(left: str, right: str) -> bool:
    return left in right or right in left
```

And add the import:

```python
from app.domain.interfaces.community_places import DEFAULT_DUPLICATE_RADIUS_METERS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (22 passed)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): detect duplicate places before insert"

# Why: two drivers adding the same roadside stop is routine on a shared
# database. Substring matching over exact equality catches "Газпром" against
# "Газпром 24" without the unpredictability of fuzzy scoring.
```

---

### Task 10: SQLite repository — `update` and `delete` with ownership

**Files:**
- Modify: `app/infrastructure/database/sqlite_places.py`
- Test: `tests/unit/test_sqlite_place_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sqlite_place_repository.py`:

```python
def test_update_changes_the_name_and_its_search_key(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", user_id=42))

    updated = repository.update(stored.id, user_id=42, name="Лукойл")

    assert updated is not None
    assert updated.name == "Лукойл"
    assert [place.name for place in repository.search(name="лукойл")] == ["Лукойл"]


def test_update_changes_the_category(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(category=PlaceCategory.FUEL, user_id=42))

    updated = repository.update(stored.id, user_id=42, category=PlaceCategory.CAFE)

    assert updated is not None
    assert updated.category is PlaceCategory.CAFE


def test_update_with_none_leaves_fields_alone(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", note="кругл", user_id=42))

    updated = repository.update(stored.id, user_id=42, category=PlaceCategory.CAFE)

    assert updated is not None
    assert updated.name == "Газпром"
    assert updated.note == "кругл"


def test_update_with_empty_note_clears_it(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(note="кругл", user_id=42))

    updated = repository.update(stored.id, user_id=42, note="")

    assert updated is not None
    assert updated.note == ""


def test_update_by_another_user_returns_none(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", user_id=42))

    assert repository.update(stored.id, user_id=7, name="Взломано") is None
    unchanged = repository.get(stored.id)
    assert unchanged is not None
    assert unchanged.name == "Газпром"


def test_delete_removes_the_place(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=42) is True
    assert repository.get(stored.id) is None


def test_delete_by_another_user_returns_false(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=7) is False
    assert repository.get(stored.id) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -k "update or delete" -v`
Expected: FAIL — `AttributeError: 'SQLitePlaceRepository' object has no attribute 'update'`

- [ ] **Step 3: Write minimal implementation**

Add to `SQLitePlaceRepository`, after `find_duplicates`:

```python
    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None:
        assignments: list[str] = []
        parameters: list[object] = []

        if name is not None:
            assignments.extend(["name = ?", "name_normalized = ?"])
            parameters.extend([name, normalize_name(name)])

        if category is not None:
            assignments.append("category = ?")
            parameters.append(category.value)

        if note is not None:
            assignments.append("note = ?")
            parameters.append(note)

        if not assignments:
            return self._get_owned(place_id, user_id)

        parameters.extend([place_id, user_id])
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE places SET {', '.join(assignments)}
                WHERE id = ? AND added_by_user_id = ?
                """,
                parameters,
            )
            connection.commit()
            if cursor.rowcount == 0:
                return None

        return self.get(place_id)

    def delete(self, place_id: int, user_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM places WHERE id = ? AND added_by_user_id = ?",
                (place_id, user_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _get_owned(self, place_id: int, user_id: int) -> Place | None:
        place = self.get(place_id)
        if place is None or place.added_by_user_id != user_id:
            return None
        return place
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_sqlite_place_repository.py -v`
Expected: PASS (35 passed — 28 already in the file plus the 7 above)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/database/sqlite_places.py tests/unit/test_sqlite_place_repository.py
git commit -m "feat(database): author-scoped place update and delete"

# Why: the author check lives in the WHERE clause rather than a read-then-write
# so a concurrent request cannot slip between the two statements.
```

---

### Task 11: In-memory repository for use case tests

**Files:**
- Create: `app/infrastructure/repositories/in_memory_places.py`
- Test: `tests/unit/test_in_memory_place_repository.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository


def make_place(
    name: str = "Газпром",
    category: PlaceCategory = PlaceCategory.FUEL,
    latitude: float = 55.75,
    longitude: float = 37.61,
    user_id: int = 42,
    note: str = "",
) -> Place:
    return Place(
        id=0,
        added_by_user_id=user_id,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        note=note,
        created_at=datetime(2026, 1, 1),
    )


def test_add_assigns_incrementing_ids() -> None:
    repository = InMemoryPlaceRepository()

    first = repository.add(make_place(name="Первое"))
    second = repository.add(make_place(name="Второе"))

    assert (first.id, second.id) == (1, 2)


def test_search_matches_normalized_name() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Газпром"))

    assert [place.name for place in repository.search(name="gazprom")] == ["Газпром"]


def test_nearby_sorts_by_distance_and_drops_far_places() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Дальше", latitude=55.7700))
    repository.add(make_place(name="Ближе", latitude=55.7510))
    repository.add(make_place(name="Слишком далеко", latitude=56.5000))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_delete_by_another_user_returns_false() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=7) is False
    assert repository.get(stored.id) is not None


def test_find_duplicates_matches_overlapping_names_in_radius() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром 24",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_in_memory_place_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.repositories.in_memory_places'`

- [ ] **Step 3: Write minimal implementation**

`app/infrastructure/repositories/in_memory_places.py`:

```python
from dataclasses import replace
from datetime import datetime, timezone

from app.application.name_normalization import normalize_name
from app.domain.entities.community_place import Place
from app.domain.interfaces.community_places import DEFAULT_DUPLICATE_RADIUS_METERS
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class InMemoryPlaceRepository:
    """Test double for PlaceRepository. Same contract, no database."""

    def __init__(self) -> None:
        self._places: dict[int, Place] = {}
        self._next_id = 1

    def add(self, place: Place) -> Place:
        # The real repository leaves created_at out of its INSERT, so the column
        # takes CURRENT_TIMESTAMP and whatever the caller passed is discarded.
        # CURRENT_TIMESTAMP is naive UTC with one-second resolution.
        stored = replace(
            place,
            id=self._next_id,
            created_at=datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
        )
        self._places[stored.id] = stored
        self._next_id += 1
        return stored

    def get(self, place_id: int) -> Place | None:
        return self._places.get(place_id)

    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        normalized_name = normalize_name(name) if name is not None else ""
        matches = [
            place
            for place in self._places.values()
            if (not normalized_name or normalized_name in normalize_name(place.name))
            and (category is None or place.category.value == category.value)
        ]
        matches.sort(key=lambda place: place.name)
        # SQLite reads a negative LIMIT as "no limit", and a double that quietly
        # truncated instead would hide the difference from the use case tests.
        return matches if limit < 0 else matches[:limit]

    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        with_distance = [
            (coordinates.distance_to(place.coordinates), place)
            for place in self._places.values()
            if category is None or place.category.value == category.value
        ]
        within = [item for item in with_distance if item[0] <= radius_meters]
        within.sort(key=lambda item: item[0])
        return [place for _, place in within[: max(limit, 0)]]

    def list_by_author(self, user_id: int) -> list[Place]:
        matches = [
            place
            for place in self._places.values()
            if place.added_by_user_id == user_id
        ]
        matches.sort(key=lambda place: place.id, reverse=True)
        return matches

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return []

        # The stored side needs the same emptiness guard as the incoming one:
        # every string contains the empty string, so one place with a blank name
        # would otherwise be reported as a duplicate of everything near it.
        return [
            place
            for place in self.nearby(coordinates, radius_meters, limit=50)
            if (stored_name := normalize_name(place.name))
            and _names_overlap(normalized_name, stored_name)
        ]

    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None:
        place = self._places.get(place_id)
        if place is None or place.added_by_user_id != user_id:
            return None

        updated = replace(
            place,
            name=place.name if name is None else name,
            category=place.category if category is None else category,
            note=place.note if note is None else note,
        )
        self._places[place_id] = updated
        return updated

    def delete(self, place_id: int, user_id: int) -> bool:
        place = self._places.get(place_id)
        if place is None or place.added_by_user_id != user_id:
            return False

        del self._places[place_id]
        return True


def _names_overlap(left: str, right: str) -> bool:
    return left in right or right in left
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_in_memory_place_repository.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: **149 passed, 1 skipped** (129 after Task 10, plus the 5 above, the 9 that land
with the follow-up fix, and the 6 from the review round that pin the blank-name update,
persistence after update and delete, the naive-UTC stamp, and the three non-enum category
paths). The old bot is untouched.

- [ ] **Step 6: Commit**

```bash
git add app/infrastructure/repositories/in_memory_places.py tests/unit/test_in_memory_place_repository.py
git commit -m "feat(repositories): add in-memory place repository"

# Why: use case and handler tests need the repository contract without paying
# for disk I/O; its own tests keep it honest against the SQLite version.
```

---

# Phase 2 — Use cases

---

### Task 12: Add, find and nearby use cases

**Files:**
- Create: `app/application/use_cases/places.py`
- Test: `tests/unit/test_place_use_cases.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from app.application.use_cases.places import (
    AddPlaceUseCase,
    FindPlacesUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository


def test_add_place_stores_the_contribution() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="M5, 120 км",
    )

    assert place.id > 0
    assert place.added_by_user_id == 42
    assert place.note == "M5, 120 км"
    assert isinstance(place.created_at, datetime)


def test_add_place_defaults_the_note_to_empty() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )

    assert place.note == ""


def test_add_place_rejects_a_blank_name() -> None:
    use_case = AddPlaceUseCase(InMemoryPlaceRepository())

    try:
        use_case.execute(
            user_id=42,
            name="   ",
            category=PlaceCategory.FUEL,
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
        )
    except ValueError:
        return
    raise AssertionError("blank name must raise ValueError")


def test_add_place_finds_duplicates_before_saving() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)
    coordinates = Coordinates(latitude=55.75, longitude=37.61)
    use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=coordinates,
    )

    duplicates = use_case.find_duplicates(name="Газпром", coordinates=coordinates)

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_places_matches_name_or_category() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    add.execute(
        user_id=42,
        name="Придорожное",
        category=PlaceCategory.RESTAURANT,
        coordinates=Coordinates(latitude=55.76, longitude=37.62),
    )
    use_case = FindPlacesUseCase(repository)

    assert [p.name for p in use_case.execute(name="gazprom")] == ["Газпром"]
    assert [p.name for p in use_case.execute(category=PlaceCategory.RESTAURANT)] == [
        "Придорожное"
    ]


def test_nearby_places_returns_closest_first() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Дальше",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7700, longitude=37.6100),
    )
    add.execute(
        user_id=42,
        name="Ближе",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    use_case = NearbyPlacesUseCase(repository)

    results = use_case.execute(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_place_use_cases.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.application.use_cases.places'`

- [ ] **Step 3: Write minimal implementation**

`app/application/use_cases/places.py`:

```python
from datetime import datetime, timezone

from app.domain.entities.community_place import Place
from app.domain.interfaces.community_places import (
    DEFAULT_DUPLICATE_RADIUS_METERS,
    PlaceRepository,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class AddPlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        user_id: int,
        name: str,
        category: PlaceCategory,
        coordinates: Coordinates,
        note: str = "",
    ) -> Place:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("name must not be blank")

        return self._repository.add(
            Place(
                id=0,
                added_by_user_id=user_id,
                name=cleaned_name,
                category=category,
                coordinates=coordinates,
                note=note.strip(),
                # Both repositories stamp their own CURRENT_TIMESTAMP and discard
                # whatever we pass here, so this value is never read back. It is
                # naive UTC — not timezone-aware — because that is what every
                # caller actually receives; the field has no default, so a value
                # still has to be supplied.
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        return self._repository.find_duplicates(
            name=name.strip(),
            coordinates=coordinates,
            radius_meters=radius_meters,
        )


class FindPlacesUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        return self._repository.search(name=name, category=category, limit=limit)


class NearbyPlacesUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        return self._repository.nearby(
            coordinates=coordinates,
            radius_meters=radius_meters,
            category=category,
            limit=limit,
        )
```

Note: this module defines a class named `NearbyPlacesUseCase`, and so does the
soon-to-be-deleted `app/application/use_cases/nearby_places.py`. They never coexist in one
import, and the old one is removed in Task 24.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_place_use_cases.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/use_cases/places.py tests/unit/test_place_use_cases.py
git commit -m "feat(application): add place contribution and lookup use cases"
```

---

### Task 13: My-places, update and delete use cases

**Files:**
- Modify: `app/application/use_cases/places.py`
- Test: `tests/unit/test_place_use_cases.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_place_use_cases.py`:

```python
from app.application.use_cases.places import (
    DeletePlaceUseCase,
    ListMyPlacesUseCase,
    UpdatePlaceUseCase,
)


def _seed(repository: InMemoryPlaceRepository, user_id: int = 42):
    return AddPlaceUseCase(repository).execute(
        user_id=user_id,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )


def test_list_my_places_returns_only_my_contributions() -> None:
    repository = InMemoryPlaceRepository()
    _seed(repository, user_id=42)
    _seed(repository, user_id=7)

    results = ListMyPlacesUseCase(repository).execute(user_id=42)

    assert [place.added_by_user_id for place in results] == [42]


def test_update_place_changes_the_category() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    updated = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id,
        user_id=42,
        category=PlaceCategory.CAFE,
    )

    assert updated is not None
    assert updated.category is PlaceCategory.CAFE


def test_update_place_by_another_user_returns_none() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    updated = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id,
        user_id=7,
        category=PlaceCategory.CAFE,
    )

    assert updated is None


def test_update_place_rejects_a_blank_name() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    try:
        UpdatePlaceUseCase(repository).execute(
            place_id=stored.id,
            user_id=42,
            name="   ",
        )
    except ValueError:
        return
    raise AssertionError("blank name must raise ValueError")


def test_delete_place_by_the_author_succeeds() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    assert DeletePlaceUseCase(repository).execute(stored.id, user_id=42) is True


def test_delete_place_by_another_user_fails() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    assert DeletePlaceUseCase(repository).execute(stored.id, user_id=7) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_place_use_cases.py -v`
Expected: FAIL — `ImportError: cannot import name 'DeletePlaceUseCase' from 'app.application.use_cases.places'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/application/use_cases/places.py`:

```python
class ListMyPlacesUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(self, user_id: int) -> list[Place]:
        return self._repository.list_by_author(user_id)


class GetPlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(self, place_id: int) -> Place | None:
        return self._repository.get(place_id)


class UpdatePlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None:
        cleaned_name = name
        if name is not None:
            # Same rule as adding one: a place has to keep a name other drivers
            # can search for. Without this a rename could blank the name, and a
            # blank name is the one case find_duplicates has to defend against.
            cleaned_name = name.strip()
            if not cleaned_name:
                raise ValueError("name must not be blank")

        return self._repository.update(
            place_id=place_id,
            user_id=user_id,
            name=cleaned_name,
            category=category,
            note=note.strip() if note is not None else None,
        )


class DeletePlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(self, place_id: int, user_id: int) -> bool:
        return self._repository.delete(place_id, user_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_place_use_cases.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: **168 passed, 1 skipped** (162 after Task 12, which added 5 tests beyond the 6
below — name and note trimming, the nearby category filter, the duplicate radius default and
the search limit default — plus one on the in-memory double, plus the 6 above)

- [ ] **Step 6: Commit**

```bash
git add app/application/use_cases/places.py tests/unit/test_place_use_cases.py
git commit -m "feat(application): add my-places, update and delete use cases"
```

---

# Phase 3 — Presentation

From here the visible bot changes. Old handlers stay registered until Task 22.

---

### Task 14: Rebuild the main menu keyboard

**Files:**
- Modify: `app/presentation/telegram/keyboards/menu.py`
- Test: `tests/unit/test_telegram_keyboards.py`

- [ ] **Step 1: Read the existing test to see what breaks**

Run: `python -m pytest tests/unit/test_telegram_keyboards.py -v`
Expected: PASS today. The current test asserts `keyboard.keyboard[2][0].text == "/cancel"`,
which the new layout changes — Step 2 replaces that assertion.

- [ ] **Step 2: Write the failing test**

Replace the whole body of `tests/unit/test_telegram_keyboards.py` with:

```python
from app.presentation.telegram.keyboards.menu import (
    ADD_PLACE_BUTTON,
    CANCEL_BUTTON,
    MY_PLACES_BUTTON,
    NEARBY_BUTTON,
    SEARCH_BUTTON,
    SETTINGS_BUTTON,
    build_main_menu_keyboard,
)


def test_main_menu_offers_every_entry_point() -> None:
    keyboard = build_main_menu_keyboard()

    labels = [button.text for row in keyboard.keyboard for button in row]

    assert labels == [
        SEARCH_BUTTON,
        NEARBY_BUTTON,
        ADD_PLACE_BUTTON,
        MY_PLACES_BUTTON,
        SETTINGS_BUTTON,
    ]


def test_main_menu_resizes() -> None:
    assert build_main_menu_keyboard().resize_keyboard is True


def test_cancel_is_a_command_not_a_menu_button() -> None:
    labels = [
        button.text for row in build_main_menu_keyboard().keyboard for button in row
    ]

    assert CANCEL_BUTTON not in labels
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_telegram_keyboards.py -v`
Expected: FAIL — `ImportError: cannot import name 'ADD_PLACE_BUTTON'`

- [ ] **Step 4: Write minimal implementation**

Replace `app/presentation/telegram/keyboards/menu.py` with:

```python
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

SEARCH_BUTTON = "🔎 Qidirish"
NEARBY_BUTTON = "📍 Yaqin atrofda"
ADD_PLACE_BUTTON = "➕ Joy qo'shish"
MY_PLACES_BUTTON = "📒 Mening joylarim"
SETTINGS_BUTTON = "⚙️ Sozlamalar"
CANCEL_BUTTON = "/cancel"


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SEARCH_BUTTON)],
            [
                KeyboardButton(text=NEARBY_BUTTON),
                KeyboardButton(text=ADD_PLACE_BUTTON),
            ],
            [
                KeyboardButton(text=MY_PLACES_BUTTON),
                KeyboardButton(text=SETTINGS_BUTTON),
            ],
        ],
        resize_keyboard=True,
    )
```

`CANCEL_BUTTON` stays exported because `/cancel` is still a command, but it no longer
occupies a menu slot — five entry points already fill the keyboard.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_telegram_keyboards.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Check what else broke**

Run: `python -m pytest -q`
Expected: FAIL — modules importing `SEARCH_LOCATION_BUTTON`, `ADD_LOCATION_BUTTON` or
`SAVED_LOCATIONS_BUTTON` raise `ImportError`. Those are
`app/presentation/telegram/handlers/search.py` and `.../saved_places.py`, both deleted in
Task 24. To keep the suite green until then, add these temporary aliases at the bottom of
`menu.py`:

```python
# Deprecated aliases kept until the old handlers are removed (Task 24).
SEARCH_LOCATION_BUTTON = SEARCH_BUTTON
ADD_LOCATION_BUTTON = ADD_PLACE_BUTTON
SAVED_LOCATIONS_BUTTON = MY_PLACES_BUTTON
```

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q`
Expected: **174 passed, 1 skipped** (173 after Task 13, which added 5 tests beyond the 6
below — GetPlaceUseCase had none, and update's trimming, note-clearing and no-op paths were
unpinned; the keyboard file went from 2 tests
to 3, and the old `test_saved_place_keyboards.py` still passes)

If a test still fails because it asserted the old three-row layout, update that assertion
to match the new labels — do not restore the old layout.

- [ ] **Step 8: Commit**

```bash
git add app/presentation/telegram/keyboards/menu.py tests/unit/test_telegram_keyboards.py
git commit -m "feat(keyboards): rebuild main menu around shared places"

# Why: search, nearby, add and my-places are now four distinct entry points
# rather than one search box, so /cancel gives up its menu slot.
```

---

### Task 15: Place keyboards

**Files:**
- Create: `app/presentation/telegram/keyboards/places.py`
- Test: `tests/unit/test_place_keyboards.py`

- [ ] **Step 1: Write the failing test**

```python
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.keyboards.places import (
    build_category_choice_keyboard,
    build_duplicate_confirmation_keyboard,
    build_my_place_actions_keyboard,
    build_place_delete_confirmation_keyboard,
    build_place_results_keyboard,
    build_update_category_keyboard,
)


def _callback_data(keyboard) -> list[str]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def test_category_choice_offers_every_category() -> None:
    keyboard = build_category_choice_keyboard("pick")

    assert _callback_data(keyboard) == [
        f"pick:{category.value}" for category in PlaceCategory
    ]


def test_place_results_carry_database_ids_not_indexes() -> None:
    keyboard = build_place_results_keyboard([101, 205])

    assert _callback_data(keyboard) == ["place:101", "place:205"]


def test_duplicate_confirmation_offers_both_answers() -> None:
    assert _callback_data(build_duplicate_confirmation_keyboard()) == [
        "add_place:duplicate:yes",
        "add_place:duplicate:no",
    ]


def test_my_place_actions_target_one_place() -> None:
    assert _callback_data(build_my_place_actions_keyboard(7)) == [
        "my_place:category:7",
        "my_place:delete:7",
    ]


def test_update_category_keyboard_targets_one_place() -> None:
    keyboard = build_update_category_keyboard(7)

    assert _callback_data(keyboard) == [
        f"my_place:set_category:7:{category.value}" for category in PlaceCategory
    ]


def test_delete_confirmation_offers_both_answers() -> None:
    assert _callback_data(build_place_delete_confirmation_keyboard(7)) == [
        "my_place:confirm_delete:7",
        "my_place:cancel_delete",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_place_keyboards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.presentation.telegram.keyboards.places'`

- [ ] **Step 3: Write minimal implementation**

`app/presentation/telegram/keyboards/places.py`:

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.keyboards.categories import category_label


def build_category_choice_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """One button per category, each callback prefixed by the caller's flow."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category_label(category),
                    callback_data=f"{prefix}:{category.value}",
                )
            ]
            for category in PlaceCategory
        ]
    )


def build_place_results_keyboard(place_ids: list[int]) -> InlineKeyboardMarkup:
    """Buttons carry the database id, so a later search cannot shift the target."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{index}", callback_data=f"place:{place_id}")]
            for index, place_id in enumerate(place_ids, start=1)
        ]
    )


def build_duplicate_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ha, qo'sh", callback_data="add_place:duplicate:yes")],
            [InlineKeyboardButton(text="❌ Yo'q", callback_data="add_place:duplicate:no")],
        ]
    )


def build_my_place_actions_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Kategoriyani o'zgartirish",
                    callback_data=f"my_place:category:{place_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="O'chirish",
                    callback_data=f"my_place:delete:{place_id}",
                )
            ],
        ]
    )


def build_update_category_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category_label(category),
                    callback_data=f"my_place:set_category:{place_id}:{category.value}",
                )
            ]
            for category in PlaceCategory
        ]
    )


def build_place_delete_confirmation_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ O'chirishni tasdiqlash",
                    callback_data=f"my_place:confirm_delete:{place_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Bekor qilish",
                    callback_data="my_place:cancel_delete",
                )
            ],
        ]
    )
```

Iterating `PlaceCategory` directly (not `editable_categories()`) guarantees no category
can silently go missing from the UI — the bug that hid `CAFE` before.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_place_keyboards.py -v`
Expected: PASS (10 passed — the 6 below plus button labels, the empty-result case
and the one-button-per-row layout, none of which the callback assertions pin)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/keyboards/places.py tests/unit/test_place_keyboards.py
git commit -m "feat(keyboards): add shared place keyboards"

# Why: buttons carry database ids instead of result indexes, so starting a
# new search mid-flow can no longer retarget a pending action.
```

---

### Task 16: Place formatters

**Files:**
- Modify: `app/presentation/telegram/formatters.py`
- Test: `tests/unit/test_place_formatters.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.formatters import (
    format_place_card,
    format_place_results,
)


def make_place(
    place_id: int = 1,
    name: str = "Газпром",
    category: PlaceCategory = PlaceCategory.FUEL,
    note: str = "",
) -> Place:
    return Place(
        id=place_id,
        added_by_user_id=42,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note=note,
        created_at=datetime(2026, 1, 1),
    )


def test_place_card_shows_name_category_and_map_link() -> None:
    text = format_place_card(make_place())

    assert "Газпром" in text
    assert "⛽" in text
    assert "55.75,37.61" in text


def test_place_card_includes_a_note_when_present() -> None:
    text = format_place_card(make_place(note="M5, 120 км"))

    assert "M5, 120 км" in text


def test_place_card_omits_the_note_line_when_empty() -> None:
    text = format_place_card(make_place(note=""))

    assert "Izoh" not in text


def test_results_are_numbered_and_show_categories() -> None:
    text = format_place_results(
        [
            make_place(place_id=1, name="Газпром", category=PlaceCategory.FUEL),
            make_place(place_id=2, name="Кафе", category=PlaceCategory.CAFE),
        ]
    )

    assert "1. Газпром" in text
    assert "2. Кафе" in text
    assert "☕" in text


def test_results_show_distance_when_given() -> None:
    text = format_place_results([make_place()], distances_meters=[1234.0])

    assert "1.2 km" in text


def test_empty_results_explain_the_database_is_the_only_source() -> None:
    text = format_place_results([])

    assert "topilmadi" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_place_formatters.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_place_card' from 'app.presentation.telegram.formatters'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/presentation/telegram/formatters.py`:

```python
NO_RESULTS_MESSAGE = (
    "Hech narsa topilmadi.\n\n"
    "Bazada faqat haydovchilar qo'shgan joylar bor. "
    "Bu joyni bilsangiz — ➕ Joy qo'shish orqali qo'shing."
)


def format_place_card(place: Place) -> str:
    latitude = place.coordinates.latitude
    longitude = place.coordinates.longitude
    note_line = f"📝 {place.note}\n" if place.note else ""

    return (
        f"📍 {place.name}\n"
        f"{category_label(place.category)}\n"
        f"{note_line}"
        f"\n{latitude}, {longitude}\n"
        f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    )


def format_place_results(
    places: list[Place],
    distances_meters: list[float] | None = None,
) -> str:
    if not places:
        return NO_RESULTS_MESSAGE

    lines: list[str] = []
    for index, place in enumerate(places, start=1):
        lines.append(f"{index}. {place.name}")
        lines.append(f"   {category_label(place.category)}")
        if distances_meters is not None and index <= len(distances_meters):
            lines.append(f"   {_format_distance(distances_meters[index - 1])}")
        if place.note:
            lines.append(f"   📝 {place.note}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_distance(meters: float) -> str:
    if meters < 1000:
        return f"{round(meters)} m"
    return f"{meters / 1000:.1f} km"
```

Add the import at the top of the module:

```python
from app.domain.entities.community_place import Place as CommunityPlace
```

and use `CommunityPlace` in the two new signatures instead of `Place`, because the module
already imports the OSM `Place` for `format_nearby_places`. Task 24 deletes the OSM import
and the alias goes away then.

Note the map link asserts `"55.75,37.61"` with no space — that is the `query=` parameter,
not the human-readable `"55.75, 37.61"` line above it. Both appear in the card.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_place_formatters.py -v`
Expected: PASS (11 passed — the 6 below plus the map link itself, sub-kilometre
distances, distance-to-place pairing, the no-distance list and result notes)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/formatters.py tests/unit/test_place_formatters.py
git commit -m "feat(formatters): render shared place cards and result lists"

# Why: an empty result now means "nobody has added this yet", so the message
# invites a contribution instead of reporting a failed lookup.
```

---

### Task 17: The add-place FSM states and the name step

**Files:**
- Create: `app/presentation/telegram/states.py`
- Create: `app/presentation/telegram/handlers/add_place.py`
- Test: `tests/unit/test_add_place_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.presentation.telegram.handlers.add_place import (
    handle_add_place_start,
    handle_name,
)
from app.presentation.telegram.states import AddPlace


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


async def test_start_asks_for_the_name() -> None:
    message = FakeMessage()
    state = make_state()

    await handle_add_place_start(message, state)

    assert await state.get_state() == AddPlace.name.state
    assert "nom" in str(message.answers[0]["text"]).lower()


async def test_name_step_stores_the_name_and_asks_for_a_category() -> None:
    state = make_state()
    await state.set_state(AddPlace.name)
    message = FakeMessage(text="  Газпром  ")

    await handle_name(message, state)

    assert (await state.get_data())["name"] == "Газпром"
    assert await state.get_state() == AddPlace.category.state
    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "add_place:category:fuel" in callback_data


async def test_name_step_rejects_a_blank_name_and_stays_put() -> None:
    state = make_state()
    await state.set_state(AddPlace.name)
    message = FakeMessage(text="   ")

    await handle_name(message, state)

    assert await state.get_state() == AddPlace.name.state
    assert "nom" in str(message.answers[0]["text"]).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_add_place_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.presentation.telegram.states'`

- [ ] **Step 3: Write minimal implementation**

`app/presentation/telegram/states.py`:

```python
from aiogram.fsm.state import State, StatesGroup


class AddPlace(StatesGroup):
    name = State()
    category = State()
    location = State()
    duplicate = State()
    note = State()


class FindPlace(StatesGroup):
    query = State()


class NearbyPlace(StatesGroup):
    location = State()
```

`app/presentation/telegram/handlers/add_place.py`:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.presentation.telegram.keyboards.menu import ADD_PLACE_BUTTON
from app.presentation.telegram.keyboards.places import build_category_choice_keyboard
from app.presentation.telegram.states import AddPlace

router = Router(name="add_place")

ASK_NAME_MESSAGE = "Joy nomini yozing. Masalan: Газпром yoki Кафе У Дороги."
ASK_CATEGORY_MESSAGE = "Kategoriyani tanlang."
BLANK_NAME_MESSAGE = "Nom bo'sh bo'lmasligi kerak. Joy nomini yozing."


@router.message(F.text == ADD_PLACE_BUTTON)
async def handle_add_place_start(message: Message, state: FSMContext) -> None:
    # Clear before setting the state: an abandoned flow leaves its name and
    # coordinates in storage, and carrying them into a fresh attempt would file
    # the new place at the old location.
    await state.set_data({})
    await state.set_state(AddPlace.name)
    await message.answer(ASK_NAME_MESSAGE)


@router.message(AddPlace.name, F.text)
async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(BLANK_NAME_MESSAGE)
        return

    await state.update_data(name=name)
    await state.set_state(AddPlace.category)
    await message.answer(
        ASK_CATEGORY_MESSAGE,
        reply_markup=build_category_choice_keyboard("add_place:category"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_add_place_handlers.py -v`
Expected: PASS (7 passed — the 3 below plus the full category keyboard, and three
tests around the rejected name: it is not stored, it offers no keyboard, and a
restarted flow drops what an abandoned one left in storage)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/states.py app/presentation/telegram/handlers/add_place.py tests/unit/test_add_place_handlers.py
git commit -m "feat(handlers): start the add-place flow with a name step"

# Why: aiogram's FSM replaces the string-mode store because a four-step flow
# needs to carry data between steps, not just a mode label.
```

---

### Task 18: The category and location steps

**Files:**
- Modify: `app/presentation/telegram/handlers/add_place.py`
- Test: `tests/unit/test_add_place_handlers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_add_place_handlers.py`:

```python
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.handlers.add_place import (
    handle_category,
    handle_location,
)


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


class FakeLocation:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


class FakeLocationMessage(FakeMessage):
    def __init__(self, latitude: float, longitude: float, user_id: int = 42) -> None:
        super().__init__(user_id=user_id)
        self.location = FakeLocation(latitude, longitude)
        self.venue = None
        self.text = None


async def test_category_step_stores_the_choice_and_asks_for_a_location() -> None:
    state = make_state()
    await state.set_state(AddPlace.category)
    await state.update_data(name="Газпром")
    callback = FakeCallbackQuery("add_place:category:fuel")

    await handle_category(callback, state)

    assert (await state.get_data())["category"] == PlaceCategory.FUEL.value
    assert await state.get_state() == AddPlace.location.state
    assert "lokatsiya" in str(callback.message.answers[0]["text"]).lower()


async def test_category_step_rejects_an_unknown_category() -> None:
    state = make_state()
    await state.set_state(AddPlace.category)
    callback = FakeCallbackQuery("add_place:category:spaceship")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    assert callback.alerts[0] is not None


async def test_location_step_stores_coordinates_from_a_telegram_location() -> None:
    repository = InMemoryPlaceRepository()
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name="Газпром", category=PlaceCategory.FUEL.value)
    message = FakeLocationMessage(latitude=55.75, longitude=37.61)

    await handle_location(message, state, add_place=AddPlaceUseCase(repository))

    data = await state.get_data()
    assert data["latitude"] == 55.75
    assert data["longitude"] == 37.61
    assert await state.get_state() == AddPlace.note.state


async def test_location_step_rejects_text_that_is_not_a_location() -> None:
    repository = InMemoryPlaceRepository()
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name="Газпром", category=PlaceCategory.FUEL.value)
    message = FakeMessage(text="не координаты")
    message.location = None
    message.venue = None

    await handle_location(message, state, add_place=AddPlaceUseCase(repository))

    assert await state.get_state() == AddPlace.location.state
```

Add these imports at the top of the test module:

```python
from app.application.use_cases.places import AddPlaceUseCase
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_add_place_handlers.py -k "category or location" -v`
Expected: FAIL — `ImportError: cannot import name 'handle_category'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/presentation/telegram/handlers/add_place.py`:

```python
@router.callback_query(AddPlace.category, F.data.startswith("add_place:category:"))
async def handle_category(callback_query: CallbackQuery, state: FSMContext) -> None:
    category = _parse_category(callback_query.data)
    if category is None:
        await callback_query.answer(INVALID_CATEGORY_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await state.update_data(category=category.value)
    await state.set_state(AddPlace.location)
    await message.answer(ASK_LOCATION_MESSAGE)
    await callback_query.answer()


@router.message(AddPlace.location)
async def handle_location(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
) -> None:
    coordinates = _coordinates_from_message(message)
    if coordinates is None:
        await message.answer(ASK_LOCATION_AGAIN_MESSAGE)
        return

    await state.update_data(
        latitude=coordinates.latitude,
        longitude=coordinates.longitude,
    )

    data = await state.get_data()
    duplicates = add_place.find_duplicates(
        name=str(data["name"]),
        coordinates=coordinates,
    )
    if duplicates:
        await state.set_state(AddPlace.duplicate)
        await message.answer(
            format_duplicate_warning(duplicates),
            reply_markup=build_duplicate_confirmation_keyboard(),
        )
        return

    await state.set_state(AddPlace.note)
    await message.answer(ASK_NOTE_MESSAGE)


def _parse_category(data: str | None) -> PlaceCategory | None:
    prefix = "add_place:category:"
    if data is None or not data.startswith(prefix):
        return None
    try:
        return PlaceCategory(data.removeprefix(prefix))
    except ValueError:
        return None


def _coordinates_from_message(message: Message) -> Coordinates | None:
    location = getattr(message, "location", None)
    if location is not None:
        return Coordinates(latitude=location.latitude, longitude=location.longitude)

    venue = getattr(message, "venue", None)
    if venue is not None and getattr(venue, "location", None) is not None:
        return Coordinates(
            latitude=venue.location.latitude,
            longitude=venue.location.longitude,
        )

    text = getattr(message, "text", None)
    if text:
        return parse_coordinates_from_text(text)

    return None
```

Add these messages next to the existing ones:

```python
ASK_LOCATION_MESSAGE = (
    "Endi lokatsiyani yuboring.\n\n"
    "📎 → Lokatsiya, yoki xarita linkini, yoki koordinatani yozing: 55.75, 37.61"
)
ASK_LOCATION_AGAIN_MESSAGE = (
    "Buni lokatsiya sifatida o'qiy olmadim. "
    "Telegram lokatsiyasini yuboring yoki koordinatani yozing: 55.75, 37.61"
)
ASK_NOTE_MESSAGE = (
    "Izoh qo'shasizmi? Masalan: M5, 120-km, kechasi ochiq.\n"
    "Kerak bo'lmasa /skip yuboring."
)
INVALID_CATEGORY_MESSAGE = "Bunday kategoriya yo'q. Ro'yxatdan tanlang."
```

And extend the imports at the top of the module:

```python
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.errors import EXPIRED_MESSAGE, answerable_message
from app.presentation.telegram.formatters import format_duplicate_warning
from app.presentation.telegram.keyboards.places import (
    build_category_choice_keyboard,
    build_duplicate_confirmation_keyboard,
)
from app.presentation.telegram.location_input import parse_coordinates_from_text
```

`format_duplicate_warning` does not exist yet — add it to
`app/presentation/telegram/formatters.py`:

```python
def format_duplicate_warning(duplicates: list[CommunityPlace]) -> str:
    names = "\n".join(
        f"• {place.name} — {category_label(place.category)}" for place in duplicates
    )
    return (
        "⚠️ Yaqin atrofda shunga o'xshash joy bor:\n\n"
        f"{names}\n\n"
        "Baribir qo'shaymi?"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_add_place_handlers.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/handlers/add_place.py app/presentation/telegram/formatters.py tests/unit/test_add_place_handlers.py
git commit -m "feat(handlers): accept category and location when adding a place"

# Why: the duplicate check runs at the location step rather than at save time,
# so the driver is warned before spending effort on a note.
```

---

### Task 19: The duplicate answer and note steps

**Files:**
- Modify: `app/presentation/telegram/handlers/add_place.py`
- Test: `tests/unit/test_add_place_handlers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_add_place_handlers.py`:

```python
from app.presentation.telegram.handlers.add_place import (
    handle_cancel,
    handle_duplicate_answer,
    handle_note,
    handle_skip_note,
)


async def _state_at_note(name: str = "Газпром") -> FSMContext:
    state = make_state()
    await state.set_state(AddPlace.note)
    await state.update_data(
        name=name,
        category=PlaceCategory.FUEL.value,
        latitude=55.75,
        longitude=37.61,
    )
    return state


async def test_note_step_saves_the_place_and_clears_the_flow() -> None:
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()
    message = FakeMessage(text="M5, 120 км")

    await handle_note(message, state, add_place=AddPlaceUseCase(repository))

    stored = repository.search(name="газпром")
    assert len(stored) == 1
    assert stored[0].note == "M5, 120 км"
    assert stored[0].added_by_user_id == 42
    assert await state.get_state() is None


async def test_skip_note_saves_the_place_without_a_note() -> None:
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()
    message = FakeMessage(text="/skip")

    await handle_skip_note(message, state, add_place=AddPlaceUseCase(repository))

    stored = repository.search(name="газпром")
    assert stored[0].note == ""
    assert await state.get_state() is None


async def test_duplicate_yes_moves_on_to_the_note_step() -> None:
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    await state.update_data(
        name="Газпром",
        category=PlaceCategory.FUEL.value,
        latitude=55.75,
        longitude=37.61,
    )
    callback = FakeCallbackQuery("add_place:duplicate:yes")

    await handle_duplicate_answer(callback, state)

    assert await state.get_state() == AddPlace.note.state


async def test_duplicate_no_abandons_the_flow() -> None:
    repository = InMemoryPlaceRepository()
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    await state.update_data(name="Газпром", category=PlaceCategory.FUEL.value)
    callback = FakeCallbackQuery("add_place:duplicate:no")

    await handle_duplicate_answer(callback, state)

    assert await state.get_state() is None
    assert repository.search() == []


async def test_cancel_clears_the_flow_at_any_step() -> None:
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name="Газпром")
    message = FakeMessage(text="/cancel")

    await handle_cancel(message, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_add_place_handlers.py -k "note or duplicate or cancel" -v`
Expected: FAIL — `ImportError: cannot import name 'handle_duplicate_answer'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/presentation/telegram/handlers/add_place.py`:

```python
@router.callback_query(AddPlace.duplicate, F.data.startswith("add_place:duplicate:"))
async def handle_duplicate_answer(
    callback_query: CallbackQuery,
    state: FSMContext,
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await state.clear()
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    if callback_query.data == "add_place:duplicate:yes":
        await state.set_state(AddPlace.note)
        await message.answer(ASK_NOTE_MESSAGE)
    else:
        await state.clear()
        await message.answer(CANCELLED_MESSAGE, reply_markup=build_main_menu_keyboard())

    await callback_query.answer()


@router.message(AddPlace.note, Command("skip"))
async def handle_skip_note(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
) -> None:
    await _save(message, state, add_place, note="")


@router.message(AddPlace.note, F.text)
async def handle_note(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
) -> None:
    await _save(message, state, add_place, note=message.text or "")


@router.message(AddPlace(), Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(CANCELLED_MESSAGE, reply_markup=build_main_menu_keyboard())


async def _save(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
    note: str,
) -> None:
    data = await state.get_data()
    user_id = user_id_of(message)
    if user_id is None:
        await state.clear()
        return

    try:
        place = add_place.execute(
            user_id=user_id,
            name=str(data["name"]),
            category=PlaceCategory(str(data["category"])),
            coordinates=Coordinates(
                latitude=float(data["latitude"]),
                longitude=float(data["longitude"]),
            ),
            note=note,
        )
    except (KeyError, ValueError) as error:
        report_service_error(error, "add place")
        await state.clear()
        await message.answer(SAVE_FAILED_MESSAGE, reply_markup=build_main_menu_keyboard())
        return
    except sqlite3.Error as error:
        report_service_error(error, "add place")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE, reply_markup=build_main_menu_keyboard())
        return

    await state.clear()
    await message.answer(
        f"✅ Saqlandi.\n\n{format_place_card(place)}",
        reply_markup=build_main_menu_keyboard(),
    )
```

Add these messages:

```python
CANCELLED_MESSAGE = "Bekor qilindi. Boshlang'ich menyuga qaytdingiz."
SAVE_FAILED_MESSAGE = "Saqlab bo'lmadi. Qaytadan urinib ko'ring."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."
```

And extend the imports:

```python
import sqlite3

from aiogram.filters import Command

from app.presentation.telegram.errors import report_service_error, user_id_of
from app.presentation.telegram.formatters import format_place_card
from app.presentation.telegram.keyboards.menu import build_main_menu_keyboard
```

`AddPlace()` as a filter matches any state in the group, so one `/cancel` handler covers
every step.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_add_place_handlers.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/handlers/add_place.py tests/unit/test_add_place_handlers.py
git commit -m "feat(handlers): finish the add-place flow with note and cancel"
```

---

### Task 20: The find-place handler

**Files:**
- Create: `app/presentation/telegram/handlers/find_place.py`
- Test: `tests/unit/test_find_place_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.places import (
    AddPlaceUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.handlers.find_place import (
    handle_category_browse,
    handle_find_start,
    handle_nearby_location,
    handle_nearby_start,
    handle_place_card,
    handle_text_query,
)
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore
from app.presentation.telegram.states import NearbyPlace


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.location = None
        self.venue = None
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeLocation:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


def seeded_repository() -> InMemoryPlaceRepository:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    add.execute(
        user_id=7,
        name="Кафе У Дороги",
        category=PlaceCategory.CAFE,
        coordinates=Coordinates(latitude=55.7700, longitude=37.6100),
    )
    return repository


async def test_find_start_offers_category_buttons() -> None:
    message = FakeMessage()

    await handle_find_start(message)

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "find:category:fuel" in callback_data


async def test_text_query_finds_a_place_across_alphabets() -> None:
    repository = seeded_repository()
    message = FakeMessage(text="gazprom")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert "Газпром" in str(message.answers[0]["text"])


async def test_text_query_with_no_match_invites_a_contribution() -> None:
    repository = InMemoryPlaceRepository()
    message = FakeMessage(text="ничего")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert "qo'shing" in str(message.answers[0]["text"])


async def test_category_browse_lists_that_category() -> None:
    repository = seeded_repository()
    callback = FakeCallbackQuery("find:category:cafe")

    await handle_category_browse(
        callback,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    text = str(callback.message.answers[0]["text"])
    assert "Кафе У Дороги" in text
    assert "Газпром" not in text


async def test_nearby_start_asks_for_a_location() -> None:
    message = FakeMessage()
    state = make_state()

    await handle_nearby_start(message, state)

    assert await state.get_state() == NearbyPlace.location.state


async def test_nearby_returns_the_closest_place_first() -> None:
    repository = seeded_repository()
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    text = str(message.answers[0]["text"])
    assert text.index("Газпром") < text.index("Кафе У Дороги")
    assert await state.get_state() is None


async def test_place_card_opens_by_database_id() -> None:
    repository = seeded_repository()
    stored = repository.search(name="газпром")[0]
    callback = FakeCallbackQuery(f"place:{stored.id}")

    await handle_place_card(callback, get_place=GetPlaceUseCase(repository))

    assert "Газпром" in str(callback.message.answers[0]["text"])


async def test_place_card_for_a_deleted_place_reports_it() -> None:
    repository = InMemoryPlaceRepository()
    callback = FakeCallbackQuery("place:999")

    await handle_place_card(callback, get_place=GetPlaceUseCase(repository))

    assert callback.alerts[0] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_find_place_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.presentation.telegram.handlers.find_place'`

- [ ] **Step 3: Write minimal implementation**

`app/presentation/telegram/handlers/find_place.py`:

```python
import sqlite3
from typing import Protocol

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.places import (
    FindPlacesUseCase,
    GetPlaceUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import (
    format_place_card,
    format_place_results,
)
from app.presentation.telegram.keyboards.menu import (
    NEARBY_BUTTON,
    SEARCH_BUTTON,
    build_main_menu_keyboard,
)
from app.presentation.telegram.keyboards.places import (
    build_category_choice_keyboard,
    build_place_results_keyboard,
)
from app.presentation.telegram.states import NearbyPlace

router = Router(name="find_place")

ASK_QUERY_MESSAGE = (
    "Joy nomini yozing yoki kategoriyani tanlang.\n"
    "Masalan: Газпром, Кафе У Дороги."
)
ASK_NEARBY_LOCATION_MESSAGE = (
    "Hozirgi lokatsiyangizni yuboring — yaqin atrofdagi joylarni ko'rsataman."
)
NOT_A_LOCATION_MESSAGE = (
    "Buni lokatsiya sifatida o'qiy olmadim. Telegram lokatsiyasini yuboring."
)
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qayta qidirib ko'ring."
PLACE_GONE_MESSAGE = "Bu joy o'chirilgan."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."


class UserSettingsStore(Protocol):
    def get(self, user_id: int) -> UserSettings:
        """Return current settings for a Telegram user."""


@router.message(F.text == SEARCH_BUTTON)
async def handle_find_start(message: Message) -> None:
    await message.answer(
        ASK_QUERY_MESSAGE,
        reply_markup=build_category_choice_keyboard("find:category"),
    )


@router.callback_query(F.data.startswith("find:category:"))
async def handle_category_browse(
    callback_query: CallbackQuery,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
) -> None:
    category = _parse_category(callback_query.data, "find:category:")
    user_id = user_id_of(callback_query)
    if category is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    limit = user_settings.get(user_id).result_limit
    try:
        places = find_places.execute(category=category, limit=limit)
    except sqlite3.Error as error:
        report_service_error(error, "category browse")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await _send_results(message, places)
    await callback_query.answer()


@router.message(F.text == NEARBY_BUTTON)
async def handle_nearby_start(message: Message, state: FSMContext) -> None:
    await state.set_state(NearbyPlace.location)
    await message.answer(ASK_NEARBY_LOCATION_MESSAGE)


@router.message(NearbyPlace.location, Command("cancel"))
async def handle_nearby_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Bekor qilindi. Boshlang'ich menyuga qaytdingiz.",
        reply_markup=build_main_menu_keyboard(),
    )


@router.message(NearbyPlace.location)
async def handle_nearby_location(
    message: Message,
    state: FSMContext,
    nearby_places: NearbyPlacesUseCase,
    user_settings: UserSettingsStore,
) -> None:
    coordinates = _coordinates_from_message(message)
    user_id = user_id_of(message)
    if coordinates is None or user_id is None:
        await message.answer(NOT_A_LOCATION_MESSAGE)
        return

    settings = user_settings.get(user_id)
    try:
        places = nearby_places.execute(
            coordinates,
            radius_meters=settings.nearby_radius_meters,
            limit=settings.result_limit,
        )
    except sqlite3.Error as error:
        report_service_error(error, "nearby search")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await state.clear()
    distances = [coordinates.distance_to(place.coordinates) for place in places]
    await _send_results(message, places, distances)


@router.callback_query(F.data.startswith("place:"))
async def handle_place_card(
    callback_query: CallbackQuery,
    get_place: GetPlaceUseCase,
) -> None:
    place_id = _parse_place_id(callback_query.data)
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    place = get_place.execute(place_id)
    if place is None:
        await callback_query.answer(PLACE_GONE_MESSAGE)
        return

    await message.answer(format_place_card(place))
    await callback_query.answer()


# Registered last inside this router: a bare text message is a name search.
@router.message(F.text)
async def handle_text_query(
    message: Message,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
) -> None:
    query = (message.text or "").strip()
    user_id = user_id_of(message)
    if not query or user_id is None:
        return

    limit = user_settings.get(user_id).result_limit
    try:
        places = find_places.execute(name=query, limit=limit)
    except sqlite3.Error as error:
        report_service_error(error, "name search")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await _send_results(message, places)


async def _send_results(message, places, distances=None) -> None:
    if not places:
        await message.answer(format_place_results([]))
        return

    await message.answer(
        format_place_results(places, distances),
        reply_markup=build_place_results_keyboard([place.id for place in places]),
    )


def _parse_category(data: str | None, prefix: str) -> PlaceCategory | None:
    if data is None or not data.startswith(prefix):
        return None
    try:
        return PlaceCategory(data.removeprefix(prefix))
    except ValueError:
        return None


def _parse_place_id(data: str | None) -> int | None:
    prefix = "place:"
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    return int(raw) if raw.isdigit() else None


def _coordinates_from_message(message: Message) -> Coordinates | None:
    location = getattr(message, "location", None)
    if location is not None:
        return Coordinates(latitude=location.latitude, longitude=location.longitude)

    venue = getattr(message, "venue", None)
    if venue is not None and getattr(venue, "location", None) is not None:
        return Coordinates(
            latitude=venue.location.latitude,
            longitude=venue.location.longitude,
        )

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_find_place_handlers.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/handlers/find_place.py tests/unit/test_find_place_handlers.py
git commit -m "feat(handlers): search shared places by name, category and distance"

# Why: the bare-text handler stays last in this router so it cannot swallow
# messages meant for an in-progress flow.
```

---

### Task 21: The my-places handler

**Files:**
- Create: `app/presentation/telegram/handlers/my_places.py`
- Test: `tests/unit/test_my_places_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
from app.application.use_cases.places import (
    AddPlaceUseCase,
    DeletePlaceUseCase,
    ListMyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.handlers.my_places import (
    NOT_YOURS_MESSAGE,
    handle_confirm_delete,
    handle_delete_prompt,
    handle_my_places,
    handle_set_category,
)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int = 42) -> None:
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


def seeded():
    repository = InMemoryPlaceRepository()
    place = AddPlaceUseCase(repository).execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    return repository, place


async def test_my_places_lists_only_my_contributions() -> None:
    repository, _ = seeded()
    AddPlaceUseCase(repository).execute(
        user_id=7,
        name="Чужое",
        category=PlaceCategory.CAFE,
        coordinates=Coordinates(latitude=55.76, longitude=37.62),
    )
    message = FakeMessage(user_id=42)

    await handle_my_places(message, list_my_places=ListMyPlacesUseCase(repository))

    text = str(message.answers[0]["text"])
    assert "Газпром" in text
    assert "Чужое" not in text


async def test_my_places_when_empty_explains_how_to_add() -> None:
    message = FakeMessage(user_id=99)

    await handle_my_places(
        message,
        list_my_places=ListMyPlacesUseCase(InMemoryPlaceRepository()),
    )

    assert "qo'sh" in str(message.answers[0]["text"]).lower()


async def test_set_category_updates_my_place() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:cafe", user_id=42
    )

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert repository.get(place.id).category is PlaceCategory.CAFE


async def test_set_category_on_someone_elses_place_is_refused() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:cafe", user_id=7
    )

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert repository.get(place.id).category is PlaceCategory.FUEL
    assert NOT_YOURS_MESSAGE in callback.alerts


async def test_delete_prompt_asks_for_confirmation() -> None:
    _, place = seeded()
    callback = FakeCallbackQuery(f"my_place:delete:{place.id}", user_id=42)

    await handle_delete_prompt(callback)

    keyboard = callback.message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert f"my_place:confirm_delete:{place.id}" in callback_data


async def test_confirm_delete_removes_my_place() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=42)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository),
    )

    assert repository.get(place.id) is None


async def test_confirm_delete_on_someone_elses_place_is_refused() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=7)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository),
    )

    assert repository.get(place.id) is not None
    assert NOT_YOURS_MESSAGE in callback.alerts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_my_places_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.presentation.telegram.handlers.my_places'`

- [ ] **Step 3: Write minimal implementation**

`app/presentation/telegram/handlers/my_places.py`:

```python
import sqlite3

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.places import (
    DeletePlaceUseCase,
    ListMyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import format_place_card
from app.presentation.telegram.keyboards.menu import MY_PLACES_BUTTON
from app.presentation.telegram.keyboards.places import (
    build_my_place_actions_keyboard,
    build_place_delete_confirmation_keyboard,
    build_update_category_keyboard,
)

router = Router(name="my_places")

EMPTY_MESSAGE = (
    "Siz hali joy qo'shmagansiz.\n\n"
    "➕ Joy qo'shish tugmasi orqali birinchi joyingizni qo'shing."
)
NOT_YOURS_MESSAGE = "Bu joyni faqat uni qo'shgan foydalanuvchi o'zgartira oladi."
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qayta urinib ko'ring."
DELETED_MESSAGE = "🗑 O'chirildi."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."


@router.message(F.text == MY_PLACES_BUTTON)
async def handle_my_places(
    message: Message,
    list_my_places: ListMyPlacesUseCase,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    try:
        places = list_my_places.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "list my places")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    if not places:
        await message.answer(EMPTY_MESSAGE)
        return

    for place in places:
        await message.answer(
            format_place_card(place),
            reply_markup=build_my_place_actions_keyboard(place.id),
        )


@router.callback_query(F.data.startswith("my_place:category:"))
async def handle_category_prompt(callback_query: CallbackQuery) -> None:
    place_id = _parse_id(callback_query.data, "my_place:category:")
    message = answerable_message(callback_query)
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Yangi kategoriyani tanlang.",
        reply_markup=build_update_category_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:set_category:"))
async def handle_set_category(
    callback_query: CallbackQuery,
    update_place: UpdatePlaceUseCase,
) -> None:
    parsed = _parse_id_and_category(callback_query.data)
    user_id = user_id_of(callback_query)
    if parsed is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    place_id, category = parsed
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        updated = update_place.execute(
            place_id=place_id,
            user_id=user_id,
            category=category,
        )
    except sqlite3.Error as error:
        report_service_error(error, "update place category")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if updated is None:
        await callback_query.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(format_place_card(updated))
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:delete:"))
async def handle_delete_prompt(callback_query: CallbackQuery) -> None:
    place_id = _parse_id(callback_query.data, "my_place:delete:")
    message = answerable_message(callback_query)
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Bu joyni o'chiraymi?",
        reply_markup=build_place_delete_confirmation_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:confirm_delete:"))
async def handle_confirm_delete(
    callback_query: CallbackQuery,
    delete_place: DeletePlaceUseCase,
) -> None:
    place_id = _parse_id(callback_query.data, "my_place:confirm_delete:")
    user_id = user_id_of(callback_query)
    if place_id is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        deleted = delete_place.execute(place_id, user_id)
    except sqlite3.Error as error:
        report_service_error(error, "delete place")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if not deleted:
        await callback_query.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(DELETED_MESSAGE)
    await callback_query.answer()


@router.callback_query(F.data == "my_place:cancel_delete")
async def handle_cancel_delete(callback_query: CallbackQuery) -> None:
    message = answerable_message(callback_query)
    if message is not None:
        await message.answer("O'chirish bekor qilindi.")
    await callback_query.answer()


def _parse_id(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    return int(raw) if raw.isdigit() else None


def _parse_id_and_category(data: str | None) -> tuple[int, PlaceCategory] | None:
    prefix = "my_place:set_category:"
    if data is None or not data.startswith(prefix):
        return None

    raw_id, separator, raw_category = data.removeprefix(prefix).partition(":")
    if not separator or not raw_id.isdigit():
        return None

    try:
        return int(raw_id), PlaceCategory(raw_category)
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_my_places_handlers.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add app/presentation/telegram/handlers/my_places.py tests/unit/test_my_places_handlers.py
git commit -m "feat(handlers): manage the places I contributed"

# Why: the refusal comes from the repository returning None/False rather than
# a separate ownership read, so there is one source of truth for who may edit.
```

---

# Phase 4 — Wiring

---

### Task 22: Rewire the dispatcher

**Files:**
- Modify: `app/presentation/telegram/bot.py`
- Modify: `app/presentation/telegram/handlers/start.py`
- Test: `tests/unit/test_telegram_bot.py`
- Test: `tests/unit/test_start_handlers.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/unit/test_telegram_bot.py` with:

```python
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.bot import create_dispatcher


def test_dispatcher_injects_every_place_dependency() -> None:
    dispatcher = create_dispatcher(InMemoryPlaceRepository())

    for key in (
        "add_place",
        "find_places",
        "nearby_places",
        "get_place",
        "list_my_places",
        "update_place",
        "delete_place",
        "user_settings",
    ):
        assert key in dispatcher.workflow_data


def test_find_place_router_is_registered_last() -> None:
    dispatcher = create_dispatcher(InMemoryPlaceRepository())

    names = [router.name for router in dispatcher.sub_routers]

    assert names[-1] == "find_place"
    assert names == ["start", "settings", "add_place", "my_places", "find_place"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_telegram_bot.py -v`
Expected: FAIL — `TypeError: create_dispatcher() missing 1 required positional argument: 'search_location'`

- [ ] **Step 3: Write minimal implementation**

Replace `app/presentation/telegram/bot.py` with:

```python
from aiogram import Bot, Dispatcher

from app.application.use_cases.places import (
    AddPlaceUseCase,
    DeletePlaceUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    ListMyPlacesUseCase,
    NearbyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.config.settings import Settings
from app.domain.interfaces.community_places import PlaceRepository
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository
from app.presentation.telegram.handlers import add_place, find_place, my_places, start
from app.presentation.telegram.handlers import settings as settings_handlers
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore


def create_dispatcher(repository: PlaceRepository) -> Dispatcher:
    dispatcher = Dispatcher(
        add_place=AddPlaceUseCase(repository),
        find_places=FindPlacesUseCase(repository),
        nearby_places=NearbyPlacesUseCase(repository),
        get_place=GetPlaceUseCase(repository),
        list_my_places=ListMyPlacesUseCase(repository),
        update_place=UpdatePlaceUseCase(repository),
        delete_place=DeletePlaceUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )
    dispatcher.include_router(start.router)
    dispatcher.include_router(settings_handlers.router)
    dispatcher.include_router(add_place.router)
    dispatcher.include_router(my_places.router)
    # find_place last: it owns the bare-text catch-all handler.
    dispatcher.include_router(find_place.router)
    return dispatcher


def create_bot(settings: Settings) -> Bot:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    return Bot(token=settings.telegram_bot_token)


def create_place_repository(settings: Settings) -> PlaceRepository:
    return SQLitePlaceRepository(settings.database_path)
```

`Dispatcher()` defaults to `MemoryStorage`, which is what the FSM flows need — no extra
argument required.

Replace the `handle_cancel` half of `app/presentation/telegram/handlers/start.py`:

```python
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.presentation.telegram.formatters import format_start_message
from app.presentation.telegram.keyboards.menu import build_main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(format_start_message(), reply_markup=build_main_menu_keyboard())


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Jarayon bekor qilindi. Boshlang'ich menyuga qaytdingiz.",
        reply_markup=build_main_menu_keyboard(),
    )
```

The two `Protocol` classes at the top of that file go away with the stores they described.

- [ ] **Step 4: Update the start-handler test**

`tests/unit/test_start_handlers.py` passes fake stores that no longer exist. Replace its
calls so both handlers receive an `FSMContext`:

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.presentation.telegram.handlers.start import handle_cancel, handle_start


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int = 42) -> None:
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


async def test_start_shows_the_main_menu() -> None:
    message = FakeMessage()

    await handle_start(message, make_state())

    labels = [
        button.text
        for row in message.answers[0]["reply_markup"].keyboard
        for button in row
    ]
    assert "🔎 Qidirish" in labels


async def test_cancel_clears_any_pending_flow() -> None:
    message = FakeMessage()
    state = make_state()
    await state.update_data(name="Газпром")

    await handle_cancel(message, state)

    assert await state.get_data() == {}
    assert "bekor" in str(message.answers[0]["text"]).lower()
```

- [ ] **Step 5: Run both tests**

Run: `python -m pytest tests/unit/test_telegram_bot.py tests/unit/test_start_handlers.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add app/presentation/telegram/bot.py app/presentation/telegram/handlers/start.py tests/unit/test_telegram_bot.py tests/unit/test_start_handlers.py
git commit -m "feat(bot): wire the dispatcher to the shared place repository"

# Why: one repository now backs every use case, so the dispatcher takes it
# directly instead of assembling providers.
```

---

### Task 23: Rewire the entry point and settings

**Files:**
- Modify: `app/main.py`
- Modify: `app/config/settings.py`
- Modify: `.env.example`
- Test: `tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/unit/test_settings.py` with:

```python
from app.config.settings import Settings, get_settings


def test_settings_read_the_token_and_database_path_from_env() -> None:
    settings = Settings.from_sources(
        env={"TELEGRAM_BOT_TOKEN": "abc", "DATABASE_PATH": "/tmp/places.sqlite3"},
        dotenv_path=None,
    )

    assert settings.telegram_bot_token == "abc"
    assert settings.database_path == "/tmp/places.sqlite3"


def test_database_path_has_a_default() -> None:
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert settings.database_path == "data/find_location.sqlite3"
    assert settings.telegram_bot_token is None


def test_settings_have_no_provider_configuration() -> None:
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert not hasattr(settings, "nominatim_base_url")
    assert not hasattr(settings, "overpass_base_url")


def test_env_overrides_dotenv(tmp_path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("TELEGRAM_BOT_TOKEN=from-file\n", encoding="utf-8")

    settings = Settings.from_sources(
        env={"TELEGRAM_BOT_TOKEN": "from-env"},
        dotenv_path=dotenv,
    )

    assert settings.telegram_bot_token == "from-env"


def test_get_settings_reads_the_process_environment() -> None:
    settings = get_settings(env={"TELEGRAM_BOT_TOKEN": "abc"}, dotenv_path=None)

    assert settings.telegram_bot_token == "abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_settings.py -v`
Expected: FAIL — `test_settings_have_no_provider_configuration` fails because
`nominatim_base_url` still exists.

- [ ] **Step 3: Write minimal implementation**

In `app/config/settings.py`, delete the three provider fields from the dataclass and from
`from_sources`. The dataclass becomes:

```python
@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str | None = None
    database_path: str = "data/find_location.sqlite3"
```

and the `from_sources` return becomes:

```python
        return cls(
            telegram_bot_token=values.get("TELEGRAM_BOT_TOKEN") or None,
            database_path=values.get("DATABASE_PATH", cls.database_path),
        )
```

`_read_dotenv` and `get_settings` stay exactly as they are.

Replace `.env.example` with:

```
TELEGRAM_BOT_TOKEN=
DATABASE_PATH=data/find_location.sqlite3
```

Replace `app/main.py`'s bot path. The current file has a `run_search` CLI path that
geocodes a query — that whole path goes, because there is no geocoder any more. The new
file:

```python
import argparse
import asyncio
import sys

from app.config.settings import get_settings
from app.presentation.telegram.bot import (
    create_bot,
    create_dispatcher,
    create_place_repository,
)
from app.shared.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shared places Telegram bot.")
    parser.parse_args(argv)

    configure_logging()
    return asyncio.run(run_bot())


async def run_bot() -> int:
    settings = get_settings()
    bot = create_bot(settings)
    dispatcher = create_dispatcher(create_place_repository(settings))
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_settings.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify the CLI still starts**

Run: `python -m app.main --help`
Expected: argparse usage text, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/config/settings.py .env.example tests/unit/test_settings.py
git commit -m "feat(config): drop provider settings and the geocoding CLI"

# Why: with no external providers there is nothing to configure and nothing to
# close, so run_bot only owns the bot session.
```

---

# Phase 5 — Removal

---

### Task 24: Delete the OSM stack and the old handlers

**Files:**
- Delete: listed below
- Modify: `app/presentation/telegram/formatters.py`
- Modify: `app/presentation/telegram/selection_store.py`
- Modify: `app/presentation/telegram/keyboards/menu.py`

- [ ] **Step 1: Delete the dead modules and their tests**

```bash
git rm -r app/infrastructure/providers/osm
git rm app/application/use_cases/search_location.py
git rm app/application/use_cases/nearby_places.py
git rm app/application/use_cases/saved_places.py
git rm app/application/query_normalization.py
git rm app/domain/interfaces/geocoding.py
git rm app/domain/interfaces/places.py
git rm app/domain/interfaces/saved_places.py
git rm app/domain/interfaces/routing.py
git rm app/domain/entities/location.py
git rm app/domain/entities/place.py
git rm app/domain/entities/saved_place.py
git rm app/infrastructure/database/sqlite_saved_places.py
git rm app/infrastructure/repositories/in_memory_saved_places.py
git rm app/presentation/telegram/handlers/search.py
git rm app/presentation/telegram/handlers/location.py
git rm app/presentation/telegram/handlers/saved_places.py
git rm app/presentation/telegram/keyboards/locations.py
git rm app/presentation/telegram/keyboards/saved_places.py
git rm -r tests/providers
git rm -r tests/integration
git rm tests/unit/test_search_location_use_case.py
git rm tests/unit/test_nearby_places.py
git rm tests/unit/test_nominatim_mapper.py
git rm tests/unit/test_saved_places.py
git rm tests/unit/test_saved_place_handlers.py
git rm tests/unit/test_saved_place_keyboards.py
git rm tests/unit/test_telegram_handlers.py
git rm tests/unit/test_handler_resilience.py
git rm tests/unit/test_telegram_selection_store.py
```

`app/domain/interfaces/routing.py` goes too — it is an unimplemented protocol with no
consumer, dead since before this change.

`test_handler_resilience.py` and `test_telegram_selection_store.py` are deleted rather
than trimmed; Task 25 re-adds the parts still worth keeping.

- [ ] **Step 2: Rename the entity and interface to their real names**

```bash
git mv app/domain/entities/community_place.py app/domain/entities/place.py
git mv app/domain/interfaces/community_places.py app/domain/interfaces/places.py
git mv tests/unit/test_community_place.py tests/unit/test_place_entity.py
```

Then update every import across the tree:

```bash
grep -rl "entities.community_place\|interfaces.community_places" app tests \
  | xargs sed -i \
      -e 's/entities\.community_place/entities.place/g' \
      -e 's/interfaces\.community_places/interfaces.places/g'
```

- [ ] **Step 3: Clean up `formatters.py`**

Remove `format_search_results`, `format_selected_location`, `format_nearby_places` and
`format_saved_place` — all four render deleted entities. Remove the now-unused imports of
`Location`, `SavedPlace` and the OSM `Place`, and drop the `CommunityPlace` alias in favor
of a plain `Place` import:

```python
from app.domain.entities.place import Place
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.keyboards.categories import category_label
```

Then replace every `CommunityPlace` annotation in the file with `Place`:

```bash
sed -i 's/CommunityPlace/Place/g' app/presentation/telegram/formatters.py
```

Update `format_start_message` to describe the new bot:

```python
def format_start_message() -> str:
    return (
        "Salom. Bu bot haydovchilar birga to'plagan manzillar bazasi.\n\n"
        "🔎 Qidirish — nom yoki kategoriya bo'yicha topish.\n"
        "📍 Yaqin atrofda — lokatsiya tashlang, yaqin joylarni ko'rsataman.\n"
        "➕ Joy qo'shish — o'zingiz bilgan joyni bazaga qo'shing.\n"
        "📒 Mening joylarim — o'zingiz qo'shgan joylar.\n"
        "⚙️ Sozlamalar — radius va natijalar soni.\n\n"
        "Shunchaki nom yozsangiz ham qidiraman. Masalan: Домодедово аэропорт."
    )
```

- [ ] **Step 3b: Rewrite `tests/unit/test_telegram_formatters.py`**

That file imports `Location` and the OSM `Place` and tests the four formatters just
deleted. Only its start-message test survives. Replace the whole file with:

```python
from app.presentation.telegram.formatters import format_start_message


def test_start_message_describes_the_shared_database() -> None:
    text = format_start_message()

    assert "manzil" in text.lower()
    assert "Домодедово аэропорт" in text


def test_start_message_lists_every_entry_point() -> None:
    text = format_start_message()

    for hint in ("Qidirish", "Yaqin atrofda", "Joy qo'shish", "Mening joylarim", "Sozlamalar"):
        assert hint in text
```

The settings formatter tests live in `tests/unit/test_settings_handlers.py`, which is
untouched — `format_user_settings` and `InMemoryUserSettingsStore` both survive.

- [ ] **Step 4: Trim `selection_store.py`**

Delete `InMemoryLocationSelectionStore` and `InMemoryAddLocationFlowStore`. Keep
`InMemoryUserSettingsStore`, `_clamp` and the `user_settings` imports. Remove the now-unused
`Location` and `PlaceCategory` imports and the `replace` import if nothing else uses it.

- [ ] **Step 5: Drop the deprecated menu aliases**

Remove these three lines added in Task 14:

```python
SEARCH_LOCATION_BUTTON = SEARCH_BUTTON
ADD_LOCATION_BUTTON = ADD_PLACE_BUTTON
SAVED_LOCATIONS_BUTTON = MY_PLACES_BUTTON
```

- [ ] **Step 6: Check for stragglers**

```bash
grep -rn "nominatim\|overpass\|SavedPlace\|Location\b\|selection_store\|add_location_flow" app/ || echo "clean"
```

Expected: `clean`, apart from `app/presentation/telegram/selection_store.py` appearing as a
module path in imports of `InMemoryUserSettingsStore` — that file keeps its name.

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. The suite is now roughly **75 passed** with no skips — the skipped test was
the live Nominatim integration test, which is gone.

If anything fails with `ImportError`, the failing module still references a deleted name;
fix the import rather than restoring the file.

- [ ] **Step 8: Verify the bot assembles**

```bash
python -c "
from app.presentation.telegram.bot import create_dispatcher
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
d = create_dispatcher(InMemoryPlaceRepository())
print('routers:', [r.name for r in d.sub_routers])
print('deps:', sorted(d.workflow_data))
"
```

Expected:
```
routers: ['start', 'settings', 'add_place', 'my_places', 'find_place']
deps: ['add_place', 'delete_place', 'find_places', 'get_place', 'list_my_places', 'nearby_places', 'update_place', 'user_settings']
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: remove the OpenStreetMap stack"

# Why: the database is now the only source of places, so the geocoding and
# Overpass providers, their use cases, entities and handlers have no callers.
```

---

### Task 25: Restore the resilience tests worth keeping

Task 24 deleted `test_handler_resilience.py` wholesale. Three of its guarantees still
apply to the new handlers and need cover.

**Files:**
- Create: `tests/unit/test_handler_resilience.py`

- [ ] **Step 1: Write the failing test**

```python
import sqlite3

from app.application.use_cases.places import GetPlaceUseCase
from app.domain.value_objects.category import PlaceCategory
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.handlers.find_place import (
    EXPIRED_MESSAGE,
    handle_place_card,
    handle_text_query,
)
from app.presentation.telegram.keyboards.categories import CATEGORY_LABELS
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


class FailingFindPlaces:
    def execute(self, **_: object):
        raise sqlite3.OperationalError("database is locked")


async def test_database_failure_tells_the_user_instead_of_crashing() -> None:
    message = FakeMessage(text="газпром")

    await handle_text_query(
        message,
        find_places=FailingFindPlaces(),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert "Baza" in str(message.answers[0]["text"])


async def test_expired_callback_message_does_not_crash() -> None:
    callback = FakeCallbackQuery("place:1", with_message=False)

    await handle_place_card(
        callback,
        get_place=GetPlaceUseCase(InMemoryPlaceRepository()),
    )

    assert callback.alerts == [EXPIRED_MESSAGE]


def test_every_category_has_a_label() -> None:
    for category in PlaceCategory:
        assert category in CATEGORY_LABELS
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_handler_resilience.py -v`
Expected: PASS (3 passed) — the handlers written in Phase 3 already satisfy all three.

If `test_database_failure_tells_the_user_instead_of_crashing` fails, the `except
sqlite3.Error` block in `handle_text_query` is missing; add it as written in Task 20.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_handler_resilience.py
git commit -m "test: cover database failure and expired callback guards"

# Why: these three guarantees survived the rewrite; the label test in
# particular is what would have caught CAFE going missing from the UI.
```

---

### Task 26: Clean up the trailing edges

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Delete: `app/presentation/telegram/keyboards/categories.py` functions that no longer apply

- [ ] **Step 1: Trim `keyboards/categories.py`**

`build_add_category_keyboard`, `build_save_confirmation_keyboard`,
`build_saved_place_actions_keyboard`, `build_update_category_keyboard` and
`build_delete_confirmation_keyboard` all reference deleted flows — `keyboards/places.py`
replaced them. Reduce the file to:

```python
from app.domain.value_objects.category import PlaceCategory

CATEGORY_LABELS: dict[PlaceCategory, str] = {
    PlaceCategory.RESTAURANT: "🍽 Oshxona",
    PlaceCategory.CAFE: "☕ Kafe",
    PlaceCategory.FUEL: "⛽ Gas quyish shaxobchasi",
    PlaceCategory.HOTEL: "🏨 Mehmonxona",
    PlaceCategory.PARKING: "🅿️ Parking",
    PlaceCategory.CAR_SERVICE: "🔧 Usta / servis",
}


def category_label(category: PlaceCategory) -> str:
    return CATEGORY_LABELS.get(category, category.value)
```

`editable_categories()` goes: `keyboards/places.py` iterates `PlaceCategory` directly, so
a category can no longer be reachable in the enum but invisible in the UI.

- [ ] **Step 2: Fix the Python version declaration**

`pyproject.toml` declares `requires-python = ">=3.12"` but the interpreter in use is
3.10.14. Nothing in this codebase needs 3.11+ syntax. Lower the floor so the declaration
matches reality:

```toml
requires-python = ">=3.10"
```

and

```toml
[tool.ruff]
line-length = 100
target-version = "py310"
```

- [ ] **Step 3: Rewrite `README.md`**

The current README says "Not included yet: Overpass nearby places", which was wrong even
before this change. Replace the feature section with:

```markdown
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

## Run

```bash
python -m app.main
```

## Run Tests

```bash
python -m pytest -q
```
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS, no failures, no skips.

- [ ] **Step 5: Verify no dead references remain**

```bash
grep -rn "editable_categories\|build_add_category_keyboard\|build_save_confirmation" app/ tests/ || echo "clean"
```

Expected: `clean`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: align README, ruff target and category keyboard with the rewrite"

# Why: requires-python claimed 3.12 while the interpreter is 3.10, and the
# README still advertised Overpass as unimplemented.
```

---

### Task 27: Manual verification against a real bot

The suite proves the units; this proves the Telegram surface. Needs a working
`TELEGRAM_BOT_TOKEN` in `.env`.

- [ ] **Step 1: Start the bot**

Run: `python -m app.main`
Expected: polling starts, no traceback.

- [ ] **Step 2: Walk the add flow**

In Telegram: `/start` → `➕ Joy qo'shish` → name `Газпром` → `⛽` → send a location →
note `M5, 120-km` → expect `✅ Saqlandi` and a card with a working Google Maps link.

- [ ] **Step 3: Prove the duplicate warning**

Add `Газпром 24` at the same spot. Expect the warning listing `Газпром`, with
`✅ Ha, qo'sh` and `❌ Yo'q`. Press `❌` — nothing is saved. Repeat and press `✅` — it saves.

- [ ] **Step 4: Prove cross-alphabet search**

Type `gazprom` with no button press. Expect the Cyrillic record back.

- [ ] **Step 5: Prove nearby**

`📍 Yaqin atrofda` → send a location near the added place. Expect it listed with a distance.
Then `⚙️ Sozlamalar` → raise the radius → repeat and confirm the wider result set.

- [ ] **Step 6: Prove ownership**

`📒 Mening joylarim` → the added places appear with action buttons. Delete one and confirm
it disappears from search too.

- [ ] **Step 7: Prove cancel**

Start the add flow, stop at the location step, send `/cancel`. Expect the main menu and no
saved record.

- [ ] **Step 8: Record the result**

If every step passes, the plan is complete. If any step fails, write the failure down,
add a regression test that reproduces it, then fix it.

---

## Self-Review

**Spec coverage:**

| Spec section | Tasks |
|---|---|
| `Place` entity | 1, 24 (rename) |
| Database schema and indexes | 4 |
| `name_normalized` and transliteration | 2, 6 |
| `PlaceRepository` protocol | 3 |
| `search` / `nearby` / `list_by_author` / `find_duplicates` / `update` / `delete` | 5–10 |
| Bounding-box then Haversine | 7 |
| Duplicate definition (equal or substring, within radius) | 9 |
| `update` None-vs-empty-string semantics | 10 |
| Main menu layout | 14 |
| Add flow, four steps plus duplicate branch | 17, 18, 19 |
| `/cancel` at every step | 19, 22 |
| Search by name, by category | 20 |
| Bare text as a name search, registered last | 20, 22 |
| Nearby from the database | 20 |
| Place card with map link | 16, 20 |
| aiogram FSM replacing string modes | 17, 22, 24 |
| Callbacks carry `place_id` | 15 |
| Author-only edit and delete | 10, 13, 21 |
| Error table (SQLite, permission, bad input) | 19, 20, 21, 25 |
| `errors.py` guards retained | 18, 20, 21, 25 |
| Config cleanup | 23 |
| Test strategy (real SQLite, in-memory fake, handler fakes) | 4–11, 17–21 |
| Deletion list | 24 |
| README | 26 |
| Test files rewritten rather than deleted | 22 (`test_start_handlers`), 24 (`test_telegram_formatters`), 25 (`test_handler_resilience`) |

No spec requirement is unassigned.

**Type consistency checked:** `Place` fields (`added_by_user_id`, `note`, `created_at`) are
identical in Tasks 1, 4, 11, 12. `PlaceRepository` method signatures in Task 3 match the
SQLite implementation (Tasks 4–10) and the in-memory one (Task 11). Use case class names
in Task 12/13 match their imports in Tasks 20, 21 and 22. Callback prefixes
(`add_place:category:`, `add_place:duplicate:`, `find:category:`, `place:`, `my_place:*`)
are identical between the keyboard builders (Task 15) and the parsers (Tasks 18, 20, 21).

**Known naming detour:** Tasks 1 and 3 create `community_place.py` /
`community_places.py`, which Task 24 renames to `place.py` / `places.py`. This is
deliberate — the old OSM modules occupy those names until Phase 5, and renaming early
would break the suite mid-plan.
