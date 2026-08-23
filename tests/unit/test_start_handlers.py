from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.presentation.telegram.handlers.start import handle_cancel, handle_start
from app.presentation.telegram.states import AddPlace


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


async def test_start_drops_a_half_finished_flow() -> None:
    # /start is the way out of a stuck wizard. Leaving the old state behind
    # would send the next message back into the middle of the add-place flow.
    message = FakeMessage()
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name="Газпром")

    await handle_start(message, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_cancel_clears_any_pending_flow() -> None:
    message = FakeMessage()
    state = make_state()
    await state.set_state(AddPlace.note)
    await state.update_data(name="Газпром")

    await handle_cancel(message, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert "bekor" in str(message.answers[0]["text"]).lower()


async def test_cancel_returns_the_main_menu() -> None:
    message = FakeMessage()

    await handle_cancel(message, make_state())

    assert message.answers[0]["reply_markup"].keyboard[0][0].text == "🔎 Qidirish"
