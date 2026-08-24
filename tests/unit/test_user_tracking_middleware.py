import sqlite3

from app.application.use_cases.admin import RecordUserVisitUseCase
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository
from app.presentation.telegram.middlewares.user_tracking import UserTrackingMiddleware


class FakeUser:
    def __init__(self, user_id: int, first_name="Ali", last_name=None, username=None) -> None:
        self.id = user_id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.full_name = " ".join(part for part in (first_name, last_name) if part)


class Handler:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, event: object, data: dict) -> str:
        self.calls += 1
        return "handled"


class ExplodingUsers(InMemoryUserRepository):
    def record_seen(self, *args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("database is locked")


def middleware_over(users) -> UserTrackingMiddleware:
    return UserTrackingMiddleware(RecordUserVisitUseCase(users))


async def test_the_sender_is_recorded() -> None:
    users = InMemoryUserRepository()

    await middleware_over(users)(Handler(), object(), {"event_from_user": FakeUser(42)})

    assert users.get(42) is not None


async def test_the_name_and_username_are_stored() -> None:
    users = InMemoryUserRepository()
    sender = FakeUser(42, first_name="Ali", last_name="Valiev", username="ali")

    await middleware_over(users)(Handler(), object(), {"event_from_user": sender})

    stored = users.get(42)
    assert (stored.full_name, stored.username) == ("Ali Valiev", "ali")


async def test_the_handler_still_runs() -> None:
    handler = Handler()

    result = await middleware_over(InMemoryUserRepository())(
        handler, object(), {"event_from_user": FakeUser(42)}
    )

    assert (handler.calls, result) == (1, "handled")


async def test_an_update_without_a_sender_is_passed_through() -> None:
    # Channel posts and some service updates carry no user. Tracking is not a
    # reason to drop them.
    handler = Handler()

    result = await middleware_over(InMemoryUserRepository())(handler, object(), {})

    assert (handler.calls, result) == (1, "handled")


async def test_a_database_failure_does_not_swallow_the_update() -> None:
    # Tracking is bookkeeping. If it breaks, the driver still gets their answer.
    handler = Handler()

    result = await middleware_over(ExplodingUsers())(
        handler, object(), {"event_from_user": FakeUser(42)}
    )

    assert (handler.calls, result) == (1, "handled")
