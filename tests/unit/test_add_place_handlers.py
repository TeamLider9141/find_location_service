import sqlite3

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.application.use_cases.access import RequestAddAccessUseCase
from app.domain.value_objects.add_access import AddAccessStatus
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.handlers.add_place import (
    handle_add_place_start,
    handle_category,
    handle_duplicate_answer,
    handle_location,
    handle_name,
    handle_note,
    handle_skip_note,
)
from app.presentation.telegram.handlers.start import handle_cancel as handle_global_cancel
from app.presentation.telegram.keyboards.places import BORDER_CATEGORIES, BORDER_GROUP_VALUE
from app.presentation.telegram.states import AddPlace


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.full_name = "Ali"
        self.username = None


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        self.sent.append((chat_id, text))


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


def access_with(status: AddAccessStatus | None, user_id: int = 42) -> InMemoryAddAccessRepository:
    access = InMemoryAddAccessRepository()
    if status is not None:
        access.set_status(user_id, status)
    return access


def allowed() -> RequestAddAccessUseCase:
    return RequestAddAccessUseCase(access_with(AddAccessStatus.APPROVED))


async def test_start_asks_for_the_name() -> None:
    message = FakeMessage()
    state = make_state()

    await handle_add_place_start(message, state, allowed(), admin_ids=())

    assert await state.get_state() == AddPlace.name.state
    assert "nom" in str(message.answers[0]["text"]).lower()


async def test_start_drops_whatever_an_abandoned_flow_left_behind() -> None:
    # A driver who walks away halfway leaves name and coordinates in storage.
    # Carrying them into the next attempt would file the new place at the old
    # location, which is exactly the wrong answer for everyone who searches it.
    state = make_state()
    await state.update_data(name="Старое", latitude=55.75, longitude=37.61)

    await handle_add_place_start(FakeMessage(), state, allowed(), admin_ids=())

    assert await state.get_data() == {}


async def test_a_stranger_is_sent_to_the_admins_not_into_the_flow() -> None:
    message = FakeMessage()
    state = make_state()
    access = access_with(None)
    bot = FakeBot()

    await handle_add_place_start(
        message, state, RequestAddAccessUseCase(access), admin_ids=(1, 2), bot=bot
    )

    assert await state.get_state() is None
    assert "admin" in str(message.answers[0]["text"]).lower()
    assert [chat_id for chat_id, _ in bot.sent] == [1, 2]
    assert access.status(42) == AddAccessStatus.PENDING


async def test_a_waiting_driver_does_not_page_the_admins_again() -> None:
    # Tapping the button ten times must not send the admins ten requests.
    message = FakeMessage()
    state = make_state()
    bot = FakeBot()

    await handle_add_place_start(
        message,
        state,
        RequestAddAccessUseCase(access_with(AddAccessStatus.PENDING)),
        admin_ids=(1,),
        bot=bot,
    )

    assert await state.get_state() is None
    assert bot.sent == []
    assert "kuting" in str(message.answers[0]["text"]).lower()


async def test_an_approved_driver_walks_straight_in() -> None:
    state = make_state()
    bot = FakeBot()

    await handle_add_place_start(FakeMessage(), state, allowed(), admin_ids=(1,), bot=bot)

    assert await state.get_state() == AddPlace.name.state
    assert bot.sent == []


async def test_a_rejected_driver_may_ask_again() -> None:
    # Admins change their minds; to the driver a permanent silence is
    # indistinguishable from a broken bot.
    access = access_with(AddAccessStatus.REJECTED)
    bot = FakeBot()

    await handle_add_place_start(
        FakeMessage(), make_state(), RequestAddAccessUseCase(access), admin_ids=(1,), bot=bot
    )

    assert access.status(42) == AddAccessStatus.PENDING
    assert len(bot.sent) == 1


async def test_an_admin_skips_their_own_gate() -> None:
    state = make_state()
    access = access_with(None)

    await handle_add_place_start(
        FakeMessage(), state, RequestAddAccessUseCase(access), admin_ids=(42,)
    )

    assert await state.get_state() == AddPlace.name.state
    # No request was filed either: the admin never asked for anything.
    assert access.status(42) is None


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
    expected = []
    for category in PlaceCategory:
        if category in BORDER_CATEGORIES:
            continue
        if category is PlaceCategory.OTHER:
            expected.append(f"add_place:category:{BORDER_GROUP_VALUE}")
        expected.append(f"add_place:category:{category.value}")
    assert callback_data == expected


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


async def _state_at_note(name: str = "Газпром") -> FSMContext:
    state = make_state()
    await state.set_state(AddPlace.note)
    await state.update_data(
        name=name,
        category=PlaceCategory.FUEL.value,
        latitude=55.75,
        longitude=37.61,
    )
    return state


class ExplodingRepository(InMemoryPlaceRepository):
    def add(self, place):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")


async def test_note_step_saves_the_place_and_clears_the_flow() -> None:
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()
    message = FakeMessage(text="M5, 120 км")

    await handle_note(message, state, add_place=AddPlaceUseCase(repository), admin_ids=())

    stored = repository.search(name="газпром")
    assert len(stored) == 1
    assert stored[0].note == "M5, 120 км"
    assert stored[0].added_by_user_id == 42
    assert await state.get_state() is None


async def test_a_saved_place_is_shown_back_with_the_main_menu() -> None:
    # The card carries the map link, so the driver can check the pin landed
    # where they meant it to before anyone else searches for it.
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()
    message = FakeMessage(text="M5, 120 км")

    await handle_note(message, state, add_place=AddPlaceUseCase(repository), admin_ids=())

    text = str(message.answers[-1]["text"])
    assert "Газпром" in text
    assert "query=55.75,37.61" in text
    assert message.answers[-1]["reply_markup"] is not None


async def test_the_place_is_saved_at_the_coordinates_the_flow_collected() -> None:
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()

    await handle_note(
        FakeMessage(text="M5"),
        state,
        add_place=AddPlaceUseCase(repository),
        admin_ids=(),
    )

    stored = repository.search(name="газпром")[0]
    assert (stored.coordinates.latitude, stored.coordinates.longitude) == (55.75, 37.61)
    assert stored.category is PlaceCategory.FUEL


async def test_skip_note_saves_the_place_without_a_note() -> None:
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()
    message = FakeMessage(text="/skip")

    await handle_skip_note(message, state, add_place=AddPlaceUseCase(repository), admin_ids=())

    stored = repository.search(name="газпром")
    assert stored[0].note == ""
    assert await state.get_state() is None


async def test_a_half_finished_flow_does_not_save_a_broken_place() -> None:
    # The location step is the only thing that puts coordinates in the state.
    # Without them the save must fail loudly rather than write a place at 0,0.
    repository = InMemoryPlaceRepository()
    state = make_state()
    await state.set_state(AddPlace.note)
    await state.update_data(name="Газпром", category=PlaceCategory.FUEL.value)
    message = FakeMessage(text="M5")

    await handle_note(message, state, add_place=AddPlaceUseCase(repository), admin_ids=())

    assert repository.search() == []
    assert await state.get_state() is None
    assert "urinib" in str(message.answers[-1]["text"]).lower()


async def test_a_database_failure_tells_the_driver_and_clears_the_flow() -> None:
    # SQLite locks under concurrent writes; the driver must not be left staring
    # at a flow that swallowed their input.
    state = await _state_at_note()
    message = FakeMessage(text="M5")

    await handle_note(
        message,
        state,
        add_place=AddPlaceUseCase(ExplodingRepository()),
        admin_ids=(),
    )

    assert await state.get_state() is None
    assert "baza" in str(message.answers[-1]["text"]).lower()


async def test_duplicate_yes_moves_on_to_the_note_step() -> None:
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    await state.update_data(
        name="Газпром",
        category=PlaceCategory.FUEL.value,
        latitude=55.75,
        longitude=37.61,
    )
    callback = FakeCallbackQuery("add_place:duplicate:yes")

    await handle_duplicate_answer(callback, state, admin_ids=())

    assert await state.get_state() == AddPlace.note.state


async def test_duplicate_yes_keeps_the_data_the_save_step_needs() -> None:
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    await state.update_data(
        name="Газпром",
        category=PlaceCategory.FUEL.value,
        latitude=55.75,
        longitude=37.61,
    )

    await handle_duplicate_answer(FakeCallbackQuery("add_place:duplicate:yes"), state, admin_ids=())

    data = await state.get_data()
    assert (data["name"], data["latitude"], data["longitude"]) == ("Газпром", 55.75, 37.61)


async def test_duplicate_no_abandons_the_flow() -> None:
    repository = InMemoryPlaceRepository()
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    await state.update_data(name="Газпром", category=PlaceCategory.FUEL.value)
    callback = FakeCallbackQuery("add_place:duplicate:no")

    await handle_duplicate_answer(callback, state, admin_ids=())

    assert await state.get_state() is None
    assert repository.search() == []


async def test_an_unreadable_duplicate_answer_abandons_rather_than_saves() -> None:
    # Anything that is not an explicit yes falls through to the cancel branch:
    # a garbled callback must not be read as consent to add a second copy.
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    await state.update_data(name="Газпром")
    callback = FakeCallbackQuery("add_place:duplicate:")

    await handle_duplicate_answer(callback, state, admin_ids=())

    assert await state.get_state() is None


async def test_a_duplicate_answer_on_an_expired_message_clears_the_flow() -> None:
    state = make_state()
    await state.set_state(AddPlace.duplicate)
    callback = FakeCallbackQuery("add_place:duplicate:yes", with_message=False)

    await handle_duplicate_answer(callback, state, admin_ids=())

    assert await state.get_state() is None
    assert callback.alerts[0] is not None


# /cancel is answered by the start router, which is included first and matches
# in any state, so that is the handler these tests drive — a per-flow one would
# never see the command.
async def test_cancel_clears_the_flow_at_any_step() -> None:
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name="Газпром")
    message = FakeMessage(text="/cancel")

    await handle_global_cancel(message, state, admin_ids=())

    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_cancel_at_the_note_step_saves_nothing() -> None:
    # The last step is one keystroke from a write; cancel has to beat it.
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()

    await handle_global_cancel(FakeMessage(text="/cancel"), state, admin_ids=())

    assert repository.search() == []
    assert await state.get_data() == {}


async def test_a_place_with_no_author_is_not_saved() -> None:
    # Channel posts and anonymous admins arrive without from_user. A place
    # stored under a placeholder author belongs to nobody: its contributor
    # could never edit or delete it, and neither could anyone else.
    repository = InMemoryPlaceRepository()
    state = await _state_at_note()
    message = FakeMessage(text="M5")
    message.from_user = None

    await handle_note(message, state, add_place=AddPlaceUseCase(repository), admin_ids=())

    assert repository.search() == []
    assert await state.get_state() is None


async def test_the_border_group_opens_its_two_members() -> None:
    # Tapping the group is not a choice yet: the state stays on the category
    # step, waiting for the real one.
    state = make_state()
    await state.set_state(AddPlace.category)
    callback = FakeCallbackQuery(f"add_place:category:{BORDER_GROUP_VALUE}")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    keyboard = callback.message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert data == ["add_place:category:border_kz", "add_place:category:border_ru"]


async def test_picking_a_border_moves_on_to_the_location() -> None:
    state = make_state()
    await state.set_state(AddPlace.category)
    callback = FakeCallbackQuery("add_place:category:border_kz")

    await handle_category(callback, state)

    assert (await state.get_data())["category"] == "border_kz"
    assert await state.get_state() == AddPlace.location.state
