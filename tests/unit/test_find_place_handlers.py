import sqlite3

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.admin import RecordSearchUseCase
from app.application.use_cases.places import (
    AddPlaceUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.domain.value_objects.user_settings import UserSettings
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository
from app.presentation.telegram.handlers.find_place import (
    handle_category_browse,
    handle_find_start,
    handle_nearby_location,
    handle_nearby_start,
    handle_place_card,
    handle_text_query,
)
from app.presentation.telegram.handlers.start import handle_cancel as handle_global_cancel
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore
from app.presentation.telegram.states import NearbyPlace


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.location = None
        self.venue = None
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeLocation:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


class ExplodingUsers:
    def record_search(self, user_id: int, query: str) -> None:
        raise sqlite3.OperationalError("database is locked")


class FixedSettingsStore:
    """A settings store pinned to one value, so a test can state the limit."""

    def __init__(self, settings: UserSettings) -> None:
        self._settings = settings

    def get(self, _user_id: int) -> UserSettings:
        return self._settings


class ExplodingRepository(InMemoryPlaceRepository):
    def search(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")

    def nearby(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


def seeded_repository() -> InMemoryPlaceRepository:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    add.execute(
        user_id=7,
        name="Кафе У Дороги",
        category=PlaceCategory.CAFE,
        coordinates=Coordinates(latitude=55.7700, longitude=37.6100),
    )
    return repository


async def test_find_start_offers_category_buttons() -> None:
    message = FakeMessage()

    await handle_find_start(message)

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "find:category:fuel" in callback_data


async def test_text_query_finds_a_place_across_alphabets() -> None:
    # The whole point of normalizing names: a driver typing on a Latin keyboard
    # finds what another driver added in Cyrillic.
    repository = seeded_repository()
    message = FakeMessage(text="gazprom")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )

    assert "Газпром" in str(message.answers[0]["text"])


async def test_text_query_results_link_to_the_place_by_id() -> None:
    repository = seeded_repository()
    stored = repository.search(name="газпром")[0]
    message = FakeMessage(text="gazprom")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callback_data == [f"place:{stored.id}"]


async def test_text_query_honours_the_result_limit() -> None:
    # "о" is in both seeded names, so the limit is what decides the count.
    repository = seeded_repository()

    unlimited = FakeMessage(text="о")
    await handle_text_query(
        unlimited,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )
    assert len(unlimited.answers[0]["reply_markup"].inline_keyboard) == 2

    limited = FakeMessage(text="о")
    await handle_text_query(
        limited,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=1)),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )
    assert len(limited.answers[0]["reply_markup"].inline_keyboard) == 1


async def test_category_browse_honours_the_result_limit() -> None:
    # Two places in one category, so the limit is what decides the count.
    repository = seeded_repository()
    AddPlaceUseCase(repository).execute(
        user_id=7,
        name="Лукойл",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7520, longitude=37.6100),
    )

    unlimited = FakeCallbackQuery("find:category:fuel")
    await handle_category_browse(
        unlimited,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )
    keyboard = unlimited.message.answers[0]["reply_markup"]
    assert len(keyboard.inline_keyboard) == 2

    limited = FakeCallbackQuery("find:category:fuel")
    await handle_category_browse(
        limited,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=1)),
    )
    keyboard = limited.message.answers[0]["reply_markup"]
    assert len(keyboard.inline_keyboard) == 1


async def test_text_query_with_no_match_invites_a_contribution() -> None:
    repository = InMemoryPlaceRepository()
    message = FakeMessage(text="ничего")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )

    assert "qo'shing" in str(message.answers[0]["text"])


async def test_a_blank_query_is_ignored_rather_than_dumping_the_database() -> None:
    # An empty name matches everything in the repository.
    repository = seeded_repository()
    message = FakeMessage(text="   ")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )

    assert message.answers == []


async def test_a_database_failure_during_search_tells_the_driver() -> None:
    message = FakeMessage(text="gazprom")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(ExplodingRepository()),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )

    assert "baza" in str(message.answers[0]["text"]).lower()


async def test_category_browse_lists_that_category() -> None:
    repository = seeded_repository()
    callback = FakeCallbackQuery("find:category:cafe")

    await handle_category_browse(
        callback,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    text = str(callback.message.answers[0]["text"])
    assert "Кафе У Дороги" in text
    assert "Газпром" not in text


async def test_category_browse_rejects_an_unknown_category() -> None:
    repository = seeded_repository()
    callback = FakeCallbackQuery("find:category:spaceship")

    await handle_category_browse(
        callback,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert callback.alerts[0] is not None
    assert callback.message.answers == []


async def test_category_browse_survives_a_message_too_old_to_answer() -> None:
    repository = seeded_repository()
    callback = FakeCallbackQuery("find:category:cafe", with_message=False)

    await handle_category_browse(
        callback,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert callback.alerts[0] is not None


async def test_nearby_start_asks_for_a_location() -> None:
    message = FakeMessage()
    state = make_state()

    await handle_nearby_start(message, state)

    assert await state.get_state() == NearbyPlace.location.state


async def test_nearby_returns_the_closest_place_first() -> None:
    repository = seeded_repository()
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    text = str(message.answers[0]["text"])
    assert text.index("Газпром") < text.index("Кафе У Дороги")
    assert await state.get_state() is None


async def test_nearby_shows_how_far_each_place_is() -> None:
    # Distance is the reason a driver chose "nearby" over a name search.
    repository = seeded_repository()
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    text = str(message.answers[0]["text"])
    assert "111 m" in text
    assert "2.2 km" in text


async def test_nearby_honours_the_configured_radius() -> None:
    repository = seeded_repository()
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(nearby_radius_meters=1_000)),
    )

    text = str(message.answers[0]["text"])
    assert "Газпром" in text
    assert "Кафе У Дороги" not in text


async def test_nearby_rejects_text_that_is_not_a_location() -> None:
    repository = seeded_repository()
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage(text="Москва")

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )

    # Still waiting for a location: the driver gets another chance rather than
    # being dropped back to the menu.
    assert await state.get_state() == NearbyPlace.location.state


async def test_a_database_failure_during_nearby_clears_the_flow() -> None:
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.75, longitude=37.61)

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(ExplodingRepository()),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert "baza" in str(message.answers[0]["text"]).lower()
    assert await state.get_state() is None


# Same as in the add-place flow: /cancel belongs to the start router, which is
# included first and matches in any state.
async def test_nearby_cancel_returns_to_the_menu() -> None:
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage(text="/cancel")

    await handle_global_cancel(message, state, admin_ids=())

    assert await state.get_state() is None
    assert message.answers[0]["reply_markup"] is not None


async def test_place_card_opens_by_database_id() -> None:
    repository = seeded_repository()
    stored = repository.search(name="газпром")[0]
    callback = FakeCallbackQuery(f"place:{stored.id}")

    await handle_place_card(callback, get_place=GetPlaceUseCase(repository))

    assert "Газпром" in str(callback.message.answers[0]["text"])


async def test_place_card_for_a_deleted_place_reports_it() -> None:
    repository = InMemoryPlaceRepository()
    callback = FakeCallbackQuery("place:999")

    await handle_place_card(callback, get_place=GetPlaceUseCase(repository))

    assert callback.alerts[0] is not None


async def test_place_card_rejects_a_callback_that_is_not_an_id() -> None:
    # int() on a non-numeric payload would raise inside the handler and leave
    # the driver with a spinner that never stops.
    repository = seeded_repository()
    callback = FakeCallbackQuery("place:abc")

    await handle_place_card(callback, get_place=GetPlaceUseCase(repository))

    assert callback.alerts[0] is not None
    assert callback.message.answers == []


async def test_place_card_is_shown_to_whoever_asks() -> None:
    # A shared database means the contributor is not the only reader.
    repository = seeded_repository()
    stored = repository.search(name="газпром")[0]
    callback = FakeCallbackQuery(f"place:{stored.id}", user_id=999)

    await handle_place_card(callback, get_place=GetPlaceUseCase(repository))

    assert "Газпром" in str(callback.message.answers[0]["text"])


async def test_a_search_is_logged_for_the_admin_panel() -> None:
    users = InMemoryUserRepository()
    message = FakeMessage(text="Газпром")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(seeded_repository()),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(users),
    )

    assert users.top_searches() == [("газпром", 1)]


async def test_a_search_with_no_match_is_still_logged() -> None:
    # What drivers fail to find is exactly what the admin needs to see.
    users = InMemoryUserRepository()
    message = FakeMessage(text="ничего")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(InMemoryPlaceRepository()),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(users),
    )

    assert users.total_searches() == 1


async def test_a_logging_failure_still_answers_the_driver() -> None:
    message = FakeMessage(text="газпром")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(seeded_repository()),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(ExplodingUsers()),
    )

    assert message.answers[0]["reply_markup"].inline_keyboard
