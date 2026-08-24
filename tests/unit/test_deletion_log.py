from datetime import datetime

import pytest

from app.application.use_cases.admin import (
    DeletePlaceAsAdminUseCase,
    ListDeletionsUseCase,
)
from app.application.use_cases.places import DeletePlaceUseCase
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.database.sqlite_deletions import SQLiteDeletionLog
from app.infrastructure.repositories.in_memory_deletions import InMemoryDeletionLog
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository


def make_place(name: str = "Газпром", user_id: int = 42) -> Place:
    return Place(
        id=0,
        added_by_user_id=user_id,
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 1, 1),
    )


@pytest.fixture(params=["memory", "sqlite"])
def log(request, tmp_path):
    if request.param == "memory":
        return InMemoryDeletionLog()
    return SQLiteDeletionLog(tmp_path / "log.sqlite3")


def test_a_recorded_deletion_keeps_the_whole_snapshot(log) -> None:
    log.record(make_place(), deleted_by=7, source="owner")

    record = log.list_recent()[0]

    assert record.place_name == "Газпром"
    assert record.category == PlaceCategory.FUEL
    assert (record.latitude, record.longitude) == (55.75, 37.61)
    assert record.added_by_user_id == 42
    assert record.deleted_by_user_id == 7
    assert record.source == "owner"
    assert isinstance(record.deleted_at, datetime)


def test_the_newest_deletion_comes_first(log) -> None:
    log.record(make_place("Birinchi"), deleted_by=7, source="owner")
    log.record(make_place("Ikkinchi"), deleted_by=7, source="admin")

    names = [record.place_name for record in log.list_recent()]

    assert names == ["Ikkinchi", "Birinchi"]


def test_the_limit_caps_the_journal_page(log) -> None:
    for index in range(5):
        log.record(make_place(f"Joy {index}"), deleted_by=7, source="owner")

    assert len(log.list_recent(limit=3)) == 3


def test_the_journal_survives_a_restart(tmp_path) -> None:
    # The journal answers "who deleted what" long after the fact, so it has to
    # outlive every restart.
    path = tmp_path / "log.sqlite3"
    SQLiteDeletionLog(path).record(make_place(), deleted_by=7, source="admin")

    assert SQLiteDeletionLog(path).list_recent()[0].place_name == "Газпром"


def test_an_owners_delete_lands_in_the_journal() -> None:
    places = InMemoryPlaceRepository()
    log = InMemoryDeletionLog()
    stored = places.add(make_place())

    DeletePlaceUseCase(places, log).execute(stored.id, user_id=42)

    record = log.list_recent()[0]
    assert (record.source, record.deleted_by_user_id) == ("owner", 42)


def test_a_refused_delete_leaves_no_trace() -> None:
    # Nothing was deleted, so there is nothing to log — a false tombstone would
    # accuse someone of a delete that never happened.
    places = InMemoryPlaceRepository()
    log = InMemoryDeletionLog()
    stored = places.add(make_place(user_id=42))

    DeletePlaceUseCase(places, log).execute(stored.id, user_id=7)

    assert log.list_recent() == []


def test_an_admins_delete_names_the_admin() -> None:
    places = InMemoryPlaceRepository()
    log = InMemoryDeletionLog()
    stored = places.add(make_place(user_id=42))

    DeletePlaceAsAdminUseCase(places, log).execute(stored.id, deleted_by=100)

    record = log.list_recent()[0]
    assert (record.source, record.deleted_by_user_id) == ("admin", 100)


def test_the_listing_resolves_ids_to_names_where_known() -> None:
    users = InMemoryUserRepository()
    users.record_seen(100, full_name="Super", username=None)
    log = InMemoryDeletionLog()
    log.record(make_place(user_id=42), deleted_by=100, source="admin")

    row = ListDeletionsUseCase(log, users).execute()[0]

    assert row.deleted_by.full_name == "Super"
    # The author was never tracked; the id is all the journal can offer.
    assert row.added_by is None
