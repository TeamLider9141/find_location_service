from datetime import datetime, timedelta

from app.application.use_cases.access import (
    DecideAddAccessUseCase,
    RequestAddAccessUseCase,
    RevokeAddAccessUseCase,
)
from app.domain.value_objects.add_access import AddAccessStatus
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository
from tests.unit.test_add_access_repository import Clock


def test_the_first_request_marks_the_driver_pending() -> None:
    access = InMemoryAddAccessRepository()

    previous = RequestAddAccessUseCase(access).execute(42)

    assert previous is None
    assert access.status(42) == AddAccessStatus.PENDING


def test_asking_again_while_pending_changes_nothing() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.PENDING)

    previous = RequestAddAccessUseCase(access).execute(42)

    assert previous == AddAccessStatus.PENDING
    assert access.status(42) == AddAccessStatus.PENDING


def test_an_approved_driver_stays_approved() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.APPROVED)

    previous = RequestAddAccessUseCase(access).execute(42)

    assert previous == AddAccessStatus.APPROVED
    assert access.status(42) == AddAccessStatus.APPROVED


def test_a_rejected_driver_becomes_pending_again() -> None:
    # Admins change their minds; to the driver a permanent silence is
    # indistinguishable from a broken bot.
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.REJECTED)

    previous = RequestAddAccessUseCase(access).execute(42)

    assert previous == AddAccessStatus.REJECTED
    assert access.status(42) == AddAccessStatus.PENDING


def test_the_admin_can_allow() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.PENDING)

    DecideAddAccessUseCase(access).execute(42, allow=True)

    assert access.status(42) == AddAccessStatus.APPROVED


def test_the_admin_can_refuse() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.PENDING)

    DecideAddAccessUseCase(access).execute(42, allow=False)

    assert access.status(42) == AddAccessStatus.REJECTED


def test_a_revoked_driver_is_back_to_never_asked() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.APPROVED)

    RevokeAddAccessUseCase(access).execute(42)

    assert access.status(42) is None


def test_a_revoked_driver_files_a_fresh_request_next_time() -> None:
    # Cleared rather than rejected: their next attempt asks the admins again
    # instead of running into a standing refusal.
    access = InMemoryAddAccessRepository()
    access.set_status(42, AddAccessStatus.APPROVED)
    RevokeAddAccessUseCase(access).execute(42)

    previous = RequestAddAccessUseCase(access).execute(42)

    assert previous is None
    assert access.status(42) == AddAccessStatus.PENDING


def test_a_days_old_request_is_heard_afresh() -> None:
    # The admins never answered, so the driver is back where they started: the
    # use case reports no previous standing, which is what makes the handler
    # announce the request to the admins a second time.
    clock = Clock(datetime(2026, 8, 26, 12, 0))
    access = InMemoryAddAccessRepository(clock=clock)
    access.set_status(42, AddAccessStatus.PENDING)
    clock.move(timedelta(hours=25))

    previous = RequestAddAccessUseCase(access).execute(42)

    assert previous is None
    assert access.status(42) == AddAccessStatus.PENDING
