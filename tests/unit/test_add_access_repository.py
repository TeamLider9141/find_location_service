import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import pytest

from app.domain.value_objects.add_access import AddAccessStatus
from app.infrastructure.database.sqlite_add_access import SQLiteAddAccessRepository
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository

# The gate reads them through the protocol, so every test runs against both.


@pytest.fixture(params=["memory", "sqlite"])
def access(request, tmp_path):
    if request.param == "memory":
        return InMemoryAddAccessRepository()
    return SQLiteAddAccessRepository(tmp_path / "access.sqlite3")


def test_a_driver_who_never_asked_has_no_status(access) -> None:
    assert access.status(42) is None


def test_a_request_is_remembered(access) -> None:
    access.set_status(42, AddAccessStatus.PENDING)

    assert access.status(42) == AddAccessStatus.PENDING


def test_the_admins_answer_replaces_the_request(access) -> None:
    access.set_status(42, AddAccessStatus.PENDING)
    access.set_status(42, AddAccessStatus.APPROVED)

    assert access.status(42) == AddAccessStatus.APPROVED


def test_one_drivers_status_says_nothing_about_another(access) -> None:
    access.set_status(42, AddAccessStatus.APPROVED)

    assert access.status(7) is None


def test_clearing_returns_the_driver_to_never_asked(access) -> None:
    access.set_status(42, AddAccessStatus.APPROVED)

    access.clear(42)

    assert access.status(42) is None


def test_clearing_a_driver_who_never_asked_is_a_no_op(access) -> None:
    access.clear(42)

    assert access.status(42) is None


def test_a_granted_permission_survives_a_restart(tmp_path) -> None:
    # The point of the SQLite implementation: an approval must not evaporate
    # on the next deploy.
    path = tmp_path / "access.sqlite3"
    SQLiteAddAccessRepository(path).set_status(42, AddAccessStatus.APPROVED)

    assert SQLiteAddAccessRepository(path).status(42) == AddAccessStatus.APPROVED


def test_every_standing_is_read_in_one_go(access) -> None:
    # The admin user list marks who may add and who is still waiting, so it
    # asks for every standing at once rather than a status query per row.
    access.set_status(1, AddAccessStatus.APPROVED)
    access.set_status(2, AddAccessStatus.PENDING)
    access.set_status(3, AddAccessStatus.REJECTED)

    assert access.statuses() == {
        1: AddAccessStatus.APPROVED,
        2: AddAccessStatus.PENDING,
        3: AddAccessStatus.REJECTED,
    }


def test_nobody_has_a_standing_before_the_first_request(access) -> None:
    assert access.statuses() == {}


def test_a_revoked_driver_leaves_the_standings(access) -> None:
    access.set_status(1, AddAccessStatus.APPROVED)
    access.clear(1)

    assert access.statuses() == {}


class Clock:
    """A hand-wound clock, so a day can pass inside a test."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def move(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture(params=["memory", "sqlite"])
def clocked(request, tmp_path):
    clock = Clock(datetime(2026, 8, 26, 12, 0))
    if request.param == "memory":
        return InMemoryAddAccessRepository(clock=clock), clock
    return SQLiteAddAccessRepository(tmp_path / "access.sqlite3", clock=clock), clock


def test_a_request_the_admins_never_answered_stops_counting_after_a_day(clocked) -> None:
    # An unanswered request must not leave a driver waiting forever: after a
    # day they stand exactly where they did before asking, free to ask again.
    access, clock = clocked
    access.set_status(1, AddAccessStatus.PENDING)

    clock.move(timedelta(hours=25))

    assert access.status(1) is None
    assert access.statuses() == {}


def test_a_request_still_counts_inside_the_day(clocked) -> None:
    access, clock = clocked
    access.set_status(1, AddAccessStatus.PENDING)

    clock.move(timedelta(hours=23))

    assert access.status(1) == AddAccessStatus.PENDING


def test_an_answered_request_never_goes_stale(clocked) -> None:
    # Only the waiting expires. A permission granted a month ago still holds,
    # and so does a refusal.
    access, clock = clocked
    access.set_status(1, AddAccessStatus.APPROVED)
    access.set_status(2, AddAccessStatus.REJECTED)

    clock.move(timedelta(days=30))

    assert access.status(1) == AddAccessStatus.APPROVED
    assert access.status(2) == AddAccessStatus.REJECTED


def test_asking_again_restarts_the_day(clocked) -> None:
    access, clock = clocked
    access.set_status(1, AddAccessStatus.PENDING)
    clock.move(timedelta(hours=25))

    access.set_status(1, AddAccessStatus.PENDING)
    clock.move(timedelta(hours=1))

    assert access.status(1) == AddAccessStatus.PENDING


def test_a_database_written_before_standings_were_dated_still_opens(tmp_path) -> None:
    # The deploy meets tables holding only (user_id, status). The column is
    # added and the rows dated at that moment, so a driver waiting across the
    # deploy gets their full day instead of expiring the instant it lands.
    path = tmp_path / "legacy.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE add_access (user_id INTEGER PRIMARY KEY, status TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO add_access VALUES (1, 'pending'), (2, 'approved')")
        connection.commit()

    clock = Clock(datetime(2026, 8, 26, 12, 0))
    access = SQLiteAddAccessRepository(path, clock=clock)

    assert access.status(1) == AddAccessStatus.PENDING
    assert access.status(2) == AddAccessStatus.APPROVED

    clock.move(timedelta(hours=25))

    assert access.status(1) is None
    assert access.status(2) == AddAccessStatus.APPROVED
