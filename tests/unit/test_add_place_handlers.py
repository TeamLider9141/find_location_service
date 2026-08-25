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
    handle_preview_change_category,
    handle_preview_save,
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
        self.markup_edits: list[object] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})

    async def edit_reply_markup(self, reply_markup: object = None, **_: object) -> None:
        self.markup_edits.append(reply_markup)


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


class ExplodingRepository(InMemoryPlaceRepository):
    def add(self, place):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")


def make_add_place(repository: InMemoryPlaceRepository | None = None) -> AddPlaceUseCase:
    return AddPlaceUseCase(repository if repository is not None else InMemoryPlaceRepository())


async def state_with(state_value, **data) -> FSMContext:
    state = make_state()
    await state.set_state(state_value)
    if data:
        await state.update_data(**data)
    return state


FULL_DATA = dict(
    latitude=55.75,
    longitude=37.61,
    categories=[PlaceCategory.FUEL.value],
    name="Газпром",
    note="",
)


# --- the gate ---------------------------------------------------------------


async def test_start_opens_at_the_location_step() -> None:
    # Location first: it is the one thing the driver has to be standing at.
    message = FakeMessage()
    state = make_state()

    await handle_add_place_start(message, state, allowed(), admin_ids=())

    assert await state.get_state() == AddPlace.location.state
    assert "lokatsiya" in str(message.answers[0]["text"]).lower()


async def test_start_drops_whatever_an_abandoned_flow_left_behind() -> None:
    # A driver who walks away halfway leaves coordinates in storage. Carrying
    # them into the next attempt would file the new place at the old location.
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

    assert await state.get_state() == AddPlace.location.state
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

    assert await state.get_state() == AddPlace.location.state
    # No request was filed either: the admin never asked for anything.
    assert access.status(42) is None


# --- location, then category, then name, then note --------------------------


async def test_location_step_stores_coordinates_and_asks_for_a_category() -> None:
    state = await state_with(AddPlace.location)
    message = FakeLocationMessage(latitude=55.75, longitude=37.61)

    await handle_location(message, state)

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (55.75, 37.61)
    assert await state.get_state() == AddPlace.category.state
    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "add_place:category:fuel" in callback_data


async def test_the_category_keyboard_offers_every_category_and_a_done_button() -> None:
    # The prefix has to match what the category handler listens for, and no
    # category may be missing from the keyboard the driver actually sees.
    state = await state_with(AddPlace.location)
    message = FakeLocationMessage(latitude=55.75, longitude=37.61)

    await handle_location(message, state)

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    expected = []
    for category in PlaceCategory:
        if category in BORDER_CATEGORIES:
            continue
        if category is PlaceCategory.OTHER:
            expected.append(f"add_place:category:{BORDER_GROUP_VALUE}")
        expected.append(f"add_place:category:{category.value}")
    expected.append("add_place:category:done")
    assert callback_data == expected


async def test_location_step_reads_a_shared_venue() -> None:
    # Sharing a business from Telegram search sends a venue, not a location.
    state = await state_with(AddPlace.location)
    message = FakeTextMessage(text="")
    message.venue = FakeVenue(latitude=55.75, longitude=37.61)

    await handle_location(message, state)

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (55.75, 37.61)


async def test_location_step_reads_typed_coordinates() -> None:
    state = await state_with(AddPlace.location)

    await handle_location(FakeTextMessage(text="55.75, 37.61"), state)

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (55.75, 37.61)


async def test_location_step_rejects_text_that_is_not_a_location() -> None:
    state = await state_with(AddPlace.location)

    await handle_location(FakeTextMessage(text="не координаты"), state)

    assert await state.get_state() == AddPlace.location.state
    assert "latitude" not in await state.get_data()


async def test_a_tap_toggles_the_category_in_place() -> None:
    # Several categories at once: a roadside complex is a fuel station and a
    # canteen at the same time. Taps toggle; the message is redrawn, not
    # re-sent, so fifty taps do not leave fifty keyboards behind.
    state = await state_with(AddPlace.category, latitude=55.75, longitude=37.61)
    callback = FakeCallbackQuery("add_place:category:fuel")

    await handle_category(callback, state)

    assert (await state.get_data())["categories"] == ["fuel"]
    assert await state.get_state() == AddPlace.category.state
    assert len(callback.message.markup_edits) == 1
    labels = [row[0].text for row in callback.message.markup_edits[0].inline_keyboard]
    assert any(label.startswith("✅") and "Gas" in label for label in labels)


async def test_a_second_tap_untoggles_it() -> None:
    state = await state_with(
        AddPlace.category, latitude=55.75, longitude=37.61, categories=["fuel"]
    )
    callback = FakeCallbackQuery("add_place:category:fuel")

    await handle_category(callback, state)

    assert (await state.get_data())["categories"] == []


async def test_two_categories_can_be_picked_together() -> None:
    state = await state_with(
        AddPlace.category, latitude=55.75, longitude=37.61, categories=["fuel"]
    )

    await handle_category(FakeCallbackQuery("add_place:category:cafe"), state)

    assert (await state.get_data())["categories"] == ["fuel", "cafe"]


async def test_done_moves_on_to_the_name() -> None:
    state = await state_with(
        AddPlace.category, latitude=55.75, longitude=37.61, categories=["fuel", "cafe"]
    )
    callback = FakeCallbackQuery("add_place:category:done")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.name.state
    assert "nom" in str(callback.message.answers[0]["text"]).lower()
    assert callback.alerts == [None]


async def test_done_with_nothing_picked_is_refused() -> None:
    state = await state_with(AddPlace.category, latitude=55.75, longitude=37.61)
    callback = FakeCallbackQuery("add_place:category:done")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    assert "bitta" in str(callback.alerts[0]).lower()


async def test_category_step_keeps_the_coordinates_it_was_given() -> None:
    state = await state_with(AddPlace.category, latitude=55.75, longitude=37.61)

    await handle_category(FakeCallbackQuery("add_place:category:fuel"), state)

    assert (await state.get_data())["latitude"] == 55.75


async def test_category_step_rejects_an_unknown_category() -> None:
    state = await state_with(AddPlace.category)
    callback = FakeCallbackQuery("add_place:category:spaceship")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    assert callback.alerts[0] is not None


async def test_category_step_survives_a_message_too_old_to_answer() -> None:
    state = await state_with(AddPlace.category)
    callback = FakeCallbackQuery("add_place:category:fuel", with_message=False)

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    assert callback.alerts[0] is not None


async def test_the_border_group_opens_its_two_members() -> None:
    state = await state_with(AddPlace.category)
    callback = FakeCallbackQuery(f"add_place:category:{BORDER_GROUP_VALUE}")

    await handle_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    keyboard = callback.message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert data == [
        "add_place:category:border_kz",
        "add_place:category:border_ru",
        "add_place:category:done",
    ]


async def test_name_step_stores_the_name_and_asks_for_a_note() -> None:
    state = await state_with(AddPlace.name, latitude=55.75, longitude=37.61)
    message = FakeMessage(text="  Газпром  ")

    await handle_name(message, state)

    assert (await state.get_data())["name"] == "Газпром"
    assert await state.get_state() == AddPlace.note.state
    assert "izoh" in str(message.answers[0]["text"]).lower()


async def test_name_step_rejects_a_blank_name_and_stays_put() -> None:
    state = await state_with(AddPlace.name)

    message = FakeMessage(text="   ")
    await handle_name(message, state)

    assert await state.get_state() == AddPlace.name.state
    assert "name" not in await state.get_data()
    assert "nom" in str(message.answers[0]["text"]).lower()


# --- the preview ------------------------------------------------------------


async def test_the_note_leads_to_a_preview_not_a_write() -> None:
    # Nothing is written yet: the driver sees the card exactly as everyone
    # else would, and only the save button commits it.
    repository = InMemoryPlaceRepository()
    state = await state_with(AddPlace.note, **{**FULL_DATA, "note": None})
    message = FakeMessage(text="M5, 120 км")

    await handle_note(message, state)

    assert repository.search() == []
    assert await state.get_state() == AddPlace.preview.state
    text = str(message.answers[0]["text"])
    assert "shunday ko'rinadi" in text
    assert "Газпром" in text
    assert "M5, 120 км" in text
    keyboard = message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert data == ["add_place:preview:save", "add_place:preview:category"]


async def test_skipping_the_note_previews_without_one() -> None:
    state = await state_with(AddPlace.note, **FULL_DATA)
    message = FakeMessage(text="/skip")

    await handle_skip_note(message, state)

    assert await state.get_state() == AddPlace.preview.state
    assert "📝" not in str(message.answers[0]["text"])


async def test_a_flow_that_lost_a_step_cannot_reach_the_preview() -> None:
    # Without coordinates the preview would promise a place that cannot be
    # saved; better to start over.
    state = await state_with(AddPlace.note, name="Газпром", category="fuel")
    message = FakeMessage(text="M5")

    await handle_note(message, state)

    assert await state.get_state() is None
    assert "urinib" in str(message.answers[0]["text"]).lower()


async def test_saving_the_preview_writes_the_place() -> None:
    repository = InMemoryPlaceRepository()
    state = await state_with(AddPlace.preview, **{**FULL_DATA, "note": "M5, 120 км"})
    callback = FakeCallbackQuery("add_place:preview:save")

    await handle_preview_save(callback, state, make_add_place(repository), admin_ids=())

    stored = repository.search(name="газпром")
    assert len(stored) == 1
    assert stored[0].note == "M5, 120 км"
    assert stored[0].added_by_user_id == 42
    assert await state.get_state() is None
    text = str(callback.message.answers[-1]["text"])
    assert "Saqlandi" in text
    assert "query=55.75,37.61" in text


async def test_the_preview_reopens_the_categories_without_losing_the_rest() -> None:
    state = await state_with(AddPlace.preview, **FULL_DATA)
    callback = FakeCallbackQuery("add_place:preview:category")

    await handle_preview_change_category(callback, state)

    assert await state.get_state() == AddPlace.category.state
    keyboard = callback.message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "add_place:category:fuel" in data
    # The name and coordinates survive the detour.
    kept = await state.get_data()
    assert (kept["name"], kept["latitude"]) == ("Газпром", 55.75)


async def test_a_recategorised_place_returns_to_the_preview() -> None:
    # The driver was already done writing; picking again must not restart the
    # name and note steps.
    state = await state_with(AddPlace.preview, **FULL_DATA)
    await handle_preview_change_category(
        FakeCallbackQuery("add_place:preview:category"), state
    )

    await handle_category(FakeCallbackQuery("add_place:category:cafe"), state)
    done = FakeCallbackQuery("add_place:category:done")
    await handle_category(done, state)

    assert await state.get_state() == AddPlace.preview.state
    assert (await state.get_data())["categories"] == ["fuel", "cafe"]
    text = str(done.message.answers[0]["text"])
    assert "shunday ko'rinadi" in text
    assert "Kafe" in text


async def test_a_place_with_no_author_is_not_saved() -> None:
    # Channel posts and anonymous admins arrive without from_user. A place
    # stored under a placeholder author belongs to nobody.
    repository = InMemoryPlaceRepository()
    state = await state_with(AddPlace.preview, **FULL_DATA)
    callback = FakeCallbackQuery("add_place:preview:save")
    callback.from_user = None

    await handle_preview_save(callback, state, make_add_place(repository), admin_ids=())

    assert repository.search() == []
    assert await state.get_state() is None


async def test_a_database_failure_tells_the_driver_and_clears_the_flow() -> None:
    state = await state_with(AddPlace.preview, **FULL_DATA)
    callback = FakeCallbackQuery("add_place:preview:save")

    await handle_preview_save(
        callback, state, AddPlaceUseCase(ExplodingRepository()), admin_ids=()
    )

    assert await state.get_state() is None
    assert "baza" in str(callback.message.answers[-1]["text"]).lower()


# --- duplicates -------------------------------------------------------------


def seeded_add_place() -> AddPlaceUseCase:
    add_place = make_add_place()
    add_place.execute(
        user_id=7,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    return add_place


async def test_saving_over_a_neighbour_asks_first() -> None:
    # The warning names what it collided with, and nothing is written until
    # the driver answers.
    add_place = seeded_add_place()
    state = await state_with(AddPlace.preview, **{**FULL_DATA, "name": "Газпром 24"})
    callback = FakeCallbackQuery("add_place:preview:save")

    await handle_preview_save(callback, state, add_place, admin_ids=())

    assert await state.get_state() == AddPlace.duplicate.state
    text = str(callback.message.answers[0]["text"])
    assert "Газпром" in text
    keyboard = callback.message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert data == ["add_place:duplicate:yes", "add_place:duplicate:no"]


async def test_a_far_away_namesake_is_not_a_duplicate() -> None:
    # Every chain has a branch in the next city; only the nearby one matters.
    add_place = make_add_place()
    add_place.execute(
        user_id=7,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=56.50, longitude=37.61),
    )
    state = await state_with(AddPlace.preview, **FULL_DATA)

    await handle_preview_save(
        FakeCallbackQuery("add_place:preview:save"), state, add_place, admin_ids=()
    )

    assert await state.get_state() is None


async def test_duplicate_yes_writes_the_place() -> None:
    # Consent is the write: the note was already taken before the preview.
    add_place = seeded_add_place()
    state = await state_with(AddPlace.duplicate, **{**FULL_DATA, "name": "Газпром 24"})
    callback = FakeCallbackQuery("add_place:duplicate:yes")

    await handle_duplicate_answer(callback, state, add_place, admin_ids=())

    assert await state.get_state() is None
    assert "Saqlandi" in str(callback.message.answers[-1]["text"])


async def test_duplicate_no_abandons_the_flow() -> None:
    repository = InMemoryPlaceRepository()
    state = await state_with(AddPlace.duplicate, **FULL_DATA)
    callback = FakeCallbackQuery("add_place:duplicate:no")

    await handle_duplicate_answer(callback, state, make_add_place(repository), admin_ids=())

    assert await state.get_state() is None
    assert repository.search() == []


async def test_an_unreadable_duplicate_answer_abandons_rather_than_saves() -> None:
    # Anything that is not an explicit yes falls through to the cancel branch:
    # a garbled callback must not be read as consent to add a second copy.
    state = await state_with(AddPlace.duplicate, **FULL_DATA)
    callback = FakeCallbackQuery("add_place:duplicate:")

    await handle_duplicate_answer(callback, state, make_add_place(), admin_ids=())

    assert await state.get_state() is None


async def test_a_duplicate_answer_on_an_expired_message_clears_the_flow() -> None:
    state = await state_with(AddPlace.duplicate)
    callback = FakeCallbackQuery("add_place:duplicate:yes", with_message=False)

    await handle_duplicate_answer(callback, state, make_add_place(), admin_ids=())

    assert await state.get_state() is None
    assert callback.alerts[0] is not None


# /cancel is answered by the start router, which is included first and matches
# in any state, so that is the handler these tests drive — a per-flow one would
# never see the command.
async def test_cancel_clears_the_flow_at_any_step() -> None:
    state = await state_with(AddPlace.preview, **FULL_DATA)

    await handle_global_cancel(FakeMessage(text="/cancel"), state, admin_ids=())

    assert await state.get_state() is None
    assert await state.get_data() == {}


class FakeLinkResolver:
    def __init__(self, final: str | None) -> None:
        self._final = final

    async def resolve(self, url: str) -> str | None:
        return self._final


async def test_a_short_map_link_is_read_as_a_location() -> None:
    # maps.app.goo.gl carries nothing itself; the resolver chases the redirect
    # and the pin in the final URL is the place.
    state = await state_with(AddPlace.location)
    message = FakeTextMessage(text="https://maps.app.goo.gl/CtkXwh38Y2wVdGhe6")
    resolver = FakeLinkResolver(
        "https://www.google.com/maps/place/X/@41.0,69.0,17z/data=!3d41.364!4d69.288"
    )

    await handle_location(message, state, link_resolver=resolver)

    data = await state.get_data()
    assert (data["latitude"], data["longitude"]) == (41.364, 69.288)
    assert await state.get_state() == AddPlace.category.state


async def test_a_short_link_that_leads_nowhere_reads_as_unreadable() -> None:
    state = await state_with(AddPlace.location)
    message = FakeTextMessage(text="https://maps.app.goo.gl/dead")

    await handle_location(message, state, link_resolver=FakeLinkResolver(None))

    assert await state.get_state() == AddPlace.location.state
    assert "o'qiy olmadim" in str(message.answers[0]["text"])
