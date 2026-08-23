from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.handlers.add_place import (
    handle_add_place_start,
    handle_category,
    handle_location,
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


class FakeVenue:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.location = FakeLocation(latitude, longitude)


class FakeTextMessage(FakeMessage):
    def __init__(self, text: str, user_id: int = 42) -> None:
        super().__init__(text=text, user_id=user_id)
        self.location = None
        self.venue = None


def make_add_place(repository: InMemoryPlaceRepository | None = None) -> AddPlaceUseCase:
    return AddPlaceUseCase(repository if repository is not None else InMemoryPlaceRepository())


async def state_at_location_step(name: str = "Газпром") -> FSMContext:
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name=name, category=PlaceCategory.FUEL.value)
    return state


async def test_category_step_stores_the_choice_and_asks_for_a_location() -> None:
    state = make_state()
    await state.set_state(AddPlace.category)
    await state.update_data(name="Газпром")
    callback = FakeCallbackQuery("add_place:category:fuel")

    await handle_category(callback, state)

    assert (await state.get_data())["category"] == PlaceCategory.FUEL.value
    assert await state.get_state() == AddPlace.location.state
    assert "lokatsiya" in str(callback.message.answers[0]["text"]).lower()


async def test_category_step_keeps_the_name_it_was_given() -> None:
    # The name was collected one step earlier; overwriting the data instead of
    # updating it would lose it and the location step would fail on the lookup.
    state = make_state()
    await state.set_state(AddPlace.category)
    await state.update_data(name="Газпром")

    await handle_category(FakeCallbackQuery("add_place:category:fuel"), state)

    assert (await state.get_data())["name"] == "Газпром"


async def test_category_step_closes_the_telegram_spinner() -> None:
    state = make_state()
    await state.set_state(AddPlace.category)
    await state.update_data(name="Газпром")
    callback = FakeCallbackQuery("add_place:category:fuel")

    await handle_category(callback, state)

    assert callback.alerts == [None]


async def test_category_step_rejects_an_unknown_category() -> None:
    state = make_state()
    await state.set_state(AddPlace.category)
    callback = FakeCallbackQuery("add_place:category:spaceship")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    assert callback.alerts[0] is not None


async def test_category_step_survives_a_message_too_old_to_answer() -> None:
    # Telegram drops the message object on callbacks older than 48 hours. The
    # place buttons live in the chat history, so this is routine, not exotic.
    state = make_state()
    await state.set_state(AddPlace.category)
    callback = FakeCallbackQuery("add_place:category:fuel", with_message=False)

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    assert callback.alerts[0] is not None


async def test_location_step_stores_coordinates_from_a_telegram_location() -> None:
    state = await state_at_location_step()
    message = FakeLocationMessage(latitude=55.75, longitude=37.61)

    await handle_location(message, state, add_place=make_add_place())

    data = await state.get_data()
    assert data["latitude"] == 55.75
    assert data["longitude"] == 37.61
    assert await state.get_state() == AddPlace.note.state


async def test_location_step_reads_a_shared_venue() -> None:
    # Sharing a business from Telegram search sends a venue, not a location.
    state = await state_at_location_step()
    message = FakeTextMessage(text="")
    message.venue = FakeVenue(latitude=55.75, longitude=37.61)

    await handle_location(message, state, add_place=make_add_place())

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (55.75, 37.61)


async def test_location_step_reads_typed_coordinates() -> None:
    state = await state_at_location_step()

    await handle_location(
        FakeTextMessage(text="55.75, 37.61"),
        state,
        add_place=make_add_place(),
    )

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (55.75, 37.61)
    assert await state.get_state() == AddPlace.note.state


async def test_location_step_rejects_text_that_is_not_a_location() -> None:
    state = await state_at_location_step()
    message = FakeTextMessage(text="не координаты")

    await handle_location(message, state, add_place=make_add_place())

    assert await state.get_state() == AddPlace.location.state


async def test_a_rejected_location_is_not_stored() -> None:
    state = await state_at_location_step()

    await handle_location(
        FakeTextMessage(text="не координаты"),
        state,
        add_place=make_add_place(),
    )

    assert "latitude" not in await state.get_data()


async def test_location_step_warns_about_a_place_someone_already_added() -> None:
    # The whole point of asking here rather than at save time: the driver finds
    # out before writing a note that the place is already in the database.
    repository = InMemoryPlaceRepository()
    add_place = AddPlaceUseCase(repository)
    add_place.execute(
        user_id=7,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    state = await state_at_location_step(name="Газпром 24")

    message = FakeLocationMessage(latitude=55.75, longitude=37.61)
    await handle_location(message, state, add_place=add_place)

    assert await state.get_state() == AddPlace.duplicate.state
    assert "Газпром" in str(message.answers[0]["text"])
    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callback_data == ["add_place:duplicate:yes", "add_place:duplicate:no"]


async def test_a_far_away_namesake_is_not_a_duplicate() -> None:
    # Every chain has a branch in the next city; only the nearby one matters.
    repository = InMemoryPlaceRepository()
    add_place = AddPlaceUseCase(repository)
    add_place.execute(
        user_id=7,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=56.50, longitude=37.61),
    )
    state = await state_at_location_step(name="Газпром")

    await handle_location(
        FakeLocationMessage(latitude=55.75, longitude=37.61),
        state,
        add_place=add_place,
    )

    assert await state.get_state() == AddPlace.note.state


async def test_the_duplicate_branch_keeps_the_coordinates_it_was_given() -> None:
    # The driver may still answer "add it anyway", and the save step reads the
    # coordinates back out of the state.
    repository = InMemoryPlaceRepository()
    add_place = AddPlaceUseCase(repository)
    add_place.execute(
        user_id=7,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    state = await state_at_location_step(name="Газпром")

    await handle_location(
        FakeLocationMessage(latitude=55.7501, longitude=37.6101),
        state,
        add_place=add_place,
    )

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (55.7501, 37.6101)
