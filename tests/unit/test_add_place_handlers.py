from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.domain.value_objects.category import PlaceCategory
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


async def test_start_drops_whatever_an_abandoned_flow_left_behind() -> None:
    # A driver who walks away halfway leaves name and coordinates in storage.
    # Carrying them into the next attempt would file the new place at the old
    # location, which is exactly the wrong answer for everyone who searches it.
    state = make_state()
    await state.update_data(name="Старое", latitude=55.75, longitude=37.61)

    await handle_add_place_start(FakeMessage(), state)

    assert await state.get_data() == {}


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


async def test_name_step_offers_every_category() -> None:
    # The prefix has to match what the category handler listens for, and no
    # category may be missing from the keyboard the driver actually sees.
    state = make_state()
    await state.set_state(AddPlace.name)
    message = FakeMessage(text="Газпром")

    await handle_name(message, state)

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callback_data == [
        f"add_place:category:{category.value}" for category in PlaceCategory
    ]


async def test_name_step_rejects_a_blank_name_and_stays_put() -> None:
    state = make_state()
    await state.set_state(AddPlace.name)
    message = FakeMessage(text="   ")

    await handle_name(message, state)

    assert await state.get_state() == AddPlace.name.state
    assert "nom" in str(message.answers[0]["text"]).lower()


async def test_a_rejected_name_is_not_stored() -> None:
    # Storing the blank would let the location step carry it forward, and a
    # blank name is the one input find_duplicates has to defend against.
    state = make_state()
    await state.set_state(AddPlace.name)

    await handle_name(FakeMessage(text="   "), state)

    assert "name" not in await state.get_data()


async def test_a_rejected_name_offers_no_category_keyboard() -> None:
    # A category keyboard under the error would let the driver skip the name.
    state = make_state()
    await state.set_state(AddPlace.name)
    message = FakeMessage(text="   ")

    await handle_name(message, state)

    assert len(message.answers) == 1
    assert "reply_markup" not in message.answers[0]
