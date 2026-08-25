"""Stand-ins for the Telegram objects the handlers receive.

Same shape as the doubles in the unit suite, kept here so the journey test can
share one set instead of importing across test modules.
"""

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.full_name = "Ali"
        self.username = None


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        self.sent.append((chat_id, text))


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []
        self.photos: list[dict[str, object]] = []
        self.markup_edits: list[object] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})

    async def answer_photo(self, photo: object, caption: str = "", **kwargs: object) -> None:
        self.photos.append({"photo": photo, "caption": caption, **kwargs})

    async def edit_reply_markup(self, reply_markup: object = None, **_: object) -> None:
        self.markup_edits.append(reply_markup)


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


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id)
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )
