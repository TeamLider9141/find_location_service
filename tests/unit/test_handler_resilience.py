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
