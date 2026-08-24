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


def test_a_granted_permission_survives_a_restart(tmp_path) -> None:
    # The point of the SQLite implementation: an approval must not evaporate
    # on the next deploy.
    path = tmp_path / "access.sqlite3"
    SQLiteAddAccessRepository(path).set_status(42, AddAccessStatus.APPROVED)

    assert SQLiteAddAccessRepository(path).status(42) == AddAccessStatus.APPROVED
