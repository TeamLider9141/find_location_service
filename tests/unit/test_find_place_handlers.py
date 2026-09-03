import sqlite3

from app.application.use_cases.access import HasAddAccessUseCase as _HasAdd
from app.infrastructure.repositories.in_memory_add_access import (
    InMemoryAddAccessRepository as _AccessRepo,
)

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.admin import RecordSearchUseCase
from app.application.use_cases.places import (
    AddPlaceUseCase,
    CountPlacesByCategoryUseCase,
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
        self.photos: list[dict[str, object]] = []
        self.edits: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})

    async def answer_photo(self, photo: object, caption: str = "", **kwargs: object) -> None:
        self.photos.append({"photo": photo, "caption": caption, **kwargs})

    async def edit_text(self, text: str, **kwargs: object) -> None:
        self.edits.append({"text": text, **kwargs})


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


class ExplodingPlaces(InMemoryPlaceRepository):
    def count_by_category(self, exclude_author_ids: tuple[int, ...] = ()) -> dict:
        raise sqlite3.OperationalError("database is locked")


def seeded_repository() -> InMemoryPlaceRepository:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    add.execute(
        user_id=7,
        name="Кафе У Дороги",
        categories=(PlaceCategory.CAFE,),
        coordinates=Coordinates(latitude=55.7700, longitude=37.6100),
    )
    return repository


async def test_find_start_offers_category_buttons() -> None:
    message = FakeMessage()

    await handle_find_start(message, CountPlacesByCategoryUseCase(seeded_repository()))

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "find:category:fuel" in callback_data


async def test_the_category_buttons_carry_their_counts() -> None:
    # A driver picks a category knowing whether anything waits behind it; an
    # empty one keeps its plain label rather than advertising "(0 ta)".
    message = FakeMessage()

    await handle_find_start(message, CountPlacesByCategoryUseCase(seeded_repository()))

    keyboard = message.answers[0]["reply_markup"]
    labels = [row[0].text for row in keyboard.inline_keyboard]
    fuel = next(label for label in labels if "Gas" in label)
    hotel = next(label for label in labels if "Mehmonxona" in label)
    assert "(1 ta)" in fuel
    assert "ta)" not in hotel


async def test_a_counting_failure_does_not_block_the_search() -> None:
    # The numbers are decoration; the keyboard is the feature.
    message = FakeMessage()

    await handle_find_start(message, CountPlacesByCategoryUseCase(ExplodingPlaces()))

    keyboard = message.answers[0]["reply_markup"]
    assert keyboard.inline_keyboard


async def test_results_go_out_as_html_without_link_previews() -> None:
    # The names are <a> links now: without parse_mode the driver would see raw
    # tags, and without the preview switch ten link cards would bury the list.
    message = FakeMessage(text="gazprom")

    await handle_text_query(
        message,
        find_places=FindPlacesUseCase(seeded_repository()),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(InMemoryUserRepository()),
    )

    answer = message.answers[0]
    assert answer["parse_mode"] == "HTML"
    assert answer["disable_web_page_preview"] is True


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
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.7520, longitude=37.6100),
    )

    unlimited = FakeCallbackQuery("find:category:fuel")
    await handle_category_browse(
        unlimited,
        find_places=FindPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        count_places_by_category=CountPlacesByCategoryUseCase(InMemoryPlaceRepository()),
    )
    keyboard = unlimited.message.answers[0]["reply_markup"]
    assert len(keyboard.inline_keyboard) == 2

    limited = FakeCallbackQuery("find:category:fuel")
    await handle_category_browse(
        limited,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=1)),
        count_places_by_category=CountPlacesByCategoryUseCase(InMemoryPlaceRepository()),
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
        count_places_by_category=CountPlacesByCategoryUseCase(InMemoryPlaceRepository()),
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
        count_places_by_category=CountPlacesByCategoryUseCase(InMemoryPlaceRepository()),
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
        count_places_by_category=CountPlacesByCategoryUseCase(InMemoryPlaceRepository()),
    )

    assert callback.alerts[0] is not None


async def test_nearby_start_asks_for_a_location_naming_the_radius() -> None:
    # The search is only as wide as a setting the driver may never have
    # opened; the prompt says so up front.
    message = FakeMessage()
    state = make_state()

    await handle_nearby_start(message, state, InMemoryUserSettingsStore())

    assert await state.get_state() == NearbyPlace.location.state
    text = str(message.answers[0]["text"])
    assert "50 km" in text
    assert "qo'shilgan" in text


async def test_an_empty_radius_suggests_widening_it() -> None:
    # The generic "nothing found" invites adding a place; here the likelier
    # fix is one tap away in the settings.
    state = make_state()
    await state.set_state(NearbyPlace.location)
    message = FakeMessage()
    message.location = FakeLocation(latitude=10.0, longitude=10.0)

    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(InMemoryPlaceRepository()),
        user_settings=InMemoryUserSettingsStore(),
    )

    text = str(message.answers[0]["text"])
    assert "50 km" in text
    assert "oshiring" in text
    assert "Sozlamalar" in text


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

    await handle_global_cancel(
        message, state, admin_ids=(), has_add_access=_HasAdd(_AccessRepo())
    )

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


async def test_the_border_group_opens_instead_of_searching() -> None:
    callback = FakeCallbackQuery("find:category:borders")

    await handle_category_browse(
        callback,
        find_places=FindPlacesUseCase(InMemoryPlaceRepository()),
        user_settings=InMemoryUserSettingsStore(),
        count_places_by_category=CountPlacesByCategoryUseCase(InMemoryPlaceRepository()),
    )

    keyboard = callback.message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert data == ["find:category:border_kz", "find:category:border_ru"]


class FakeRoadRouter:
    def __init__(self, distances: list[float] | None) -> None:
        self._distances = distances
        self.asked: list[tuple[float, float]] = []

    async def road_distances(self, origin, destinations):
        self.asked = [(point.latitude, point.longitude) for point in destinations]
        return self._distances


async def _nearby(message, repository, road_router=None) -> None:
    state = make_state()
    await state.set_state(NearbyPlace.location)
    await handle_nearby_location(
        message,
        state,
        nearby_places=NearbyPlacesUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        road_router=road_router,
    )


async def test_nearby_resorts_by_road_distance() -> None:
    # The nearest by air is across the river; by road the other one wins.
    repository = seeded_repository()  # Газпром ~110 m, Кафе ~2.2 km by air
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)
    router = FakeRoadRouter([15_000.0, 3_000.0])

    await _nearby(message, repository, router)

    text = str(message.answers[-1]["text"])
    assert text.index("Кафе") < text.index("Газпром")
    assert "3.0 km" in text
    assert "yo'l bo'yicha" in text


async def test_the_driver_is_told_to_wait_while_roads_are_measured() -> None:
    repository = seeded_repository()
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await _nearby(message, repository, FakeRoadRouter([100.0, 200.0]))

    assert "kuting" in str(message.answers[0]["text"]).lower()


async def test_a_dead_routing_service_falls_back_to_the_straight_line() -> None:
    repository = seeded_repository()
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await _nearby(message, repository, FakeRoadRouter(None))

    text = str(message.answers[-1]["text"])
    assert text.index("Газпром") < text.index("Кафе")
    assert "to'g'ri chiziq bo'yicha" in text


async def test_without_a_router_there_is_no_wait_notice() -> None:
    # No call will be made, so there is nothing to wait for.
    repository = seeded_repository()
    message = FakeMessage()
    message.location = FakeLocation(latitude=55.7500, longitude=37.6100)

    await _nearby(message, repository, road_router=None)

    assert all("kuting" not in str(answer["text"]).lower() for answer in message.answers)
    assert "to'g'ri chiziq bo'yicha" in str(message.answers[-1]["text"])


class FakeOverviewMap:
    def __init__(self, image: bytes | None) -> None:
        self._image = image
        self.rendered: list[int] = []

    async def render(self, points):
        self.rendered.append(len(points))
        return self._image


async def test_nearby_start_sends_the_overview_sketch() -> None:
    # The driver sees what the database even holds before sharing where they
    # are; the prompt rides along as the caption.
    message = FakeMessage()
    overview = FakeOverviewMap(b"png")

    await handle_nearby_start(
        message,
        make_state(),
        InMemoryUserSettingsStore(),
        find_places=FindPlacesUseCase(seeded_repository()),
        overview_map=overview,
    )

    assert overview.rendered == [2]
    assert len(message.photos) == 1
    caption = str(message.photos[0]["caption"])
    assert "Homaki xarita" in caption
    assert "50 km" in caption
    assert message.answers == []


async def test_a_failed_sketch_falls_back_to_the_plain_prompt() -> None:
    message = FakeMessage()

    await handle_nearby_start(
        message,
        make_state(),
        InMemoryUserSettingsStore(),
        find_places=FindPlacesUseCase(seeded_repository()),
        overview_map=FakeOverviewMap(None),
    )

    assert message.photos == []
    assert "50 km" in str(message.answers[0]["text"])


async def test_an_empty_database_needs_no_sketch() -> None:
    message = FakeMessage()
    overview = FakeOverviewMap(b"png")

    await handle_nearby_start(
        message,
        make_state(),
        InMemoryUserSettingsStore(),
        find_places=FindPlacesUseCase(InMemoryPlaceRepository()),
        overview_map=overview,
    )

    assert overview.rendered == []
    assert message.photos == []
    assert len(message.answers) == 1


async def test_without_a_renderer_the_prompt_is_unchanged() -> None:
    message = FakeMessage()

    await handle_nearby_start(message, make_state(), InMemoryUserSettingsStore())

    assert message.photos == []
    assert "50 km" in str(message.answers[0]["text"])


def test_the_legend_matches_the_renderers_marker_styles() -> None:
    # Two copies of one truth: the badge table here and the marker styles in
    # the Google renderer. This is the test that keeps them in step.
    from app.infrastructure.maps.google_static import _CATEGORY_STYLES
    from app.presentation.telegram.handlers.find_place import CATEGORY_BADGES

    color_dots = {
        "orange": "🟠", "brown": "🟤", "red": "🔴", "blue": "🔵",
        "gray": "⚪", "black": "⚫", "green": "🟢", "yellow": "🟡",
        "white": "⚪",
    }
    assert set(CATEGORY_BADGES) == set(_CATEGORY_STYLES)
    for category, style in _CATEGORY_STYLES.items():
        color = style.split("|")[0].removeprefix("color:")
        letter = style.split("label:")[1]
        assert CATEGORY_BADGES[category] == f"{color_dots[color]} {letter}"


def test_the_legend_names_only_what_the_picture_shows() -> None:
    from app.presentation.telegram.handlers.find_place import overview_legend

    repository = seeded_repository()  # one fuel place, one cafe place

    legend = overview_legend(repository.search(limit=-1))

    assert "🔴 F — ⛽" in legend
    assert "🟤 C — ☕" in legend
    assert "Mehmonxona" not in legend
    assert "🟣" not in legend


def test_a_multi_category_place_earns_the_purple_line() -> None:
    from app.presentation.telegram.handlers.find_place import (
        MULTI_BADGE_LINE,
        overview_legend,
    )

    repository = InMemoryPlaceRepository()
    AddPlaceUseCase(repository).execute(
        user_id=42,
        name="Kompleks",
        categories=(PlaceCategory.FUEL, PlaceCategory.RESTAURANT),
        coordinates=Coordinates(latitude=41.3, longitude=69.2),
    )

    legend = overview_legend(repository.search(limit=-1))

    assert legend == MULTI_BADGE_LINE


async def test_the_sketch_caption_carries_the_legend() -> None:
    message = FakeMessage()

    await handle_nearby_start(
        message,
        make_state(),
        InMemoryUserSettingsStore(),
        find_places=FindPlacesUseCase(seeded_repository()),
        overview_map=FakeOverviewMap(b"png"),
    )

    caption = str(message.photos[0]["caption"])
    assert "🔴 F — ⛽" in caption
    assert "🟤 C — ☕" in caption


async def test_search_results_carry_the_places_documents() -> None:
    from app.application.use_cases.documents import (
        AddDocumentUseCase,
        DocumentsForPlacesUseCase,
    )
    from app.infrastructure.repositories.in_memory_documents import (
        InMemoryDocumentRepository,
    )

    repository = seeded_repository()
    place = repository.search(name="газпром")[0]
    documents = InMemoryDocumentRepository()
    AddDocumentUseCase(documents, repository).execute(
        user_id=42, place_id=place.id, note="Tex passport va CMR"
    )
    message = FakeMessage(text="газпром")

    await handle_text_query(
        message,
        FindPlacesUseCase(repository),
        InMemoryUserSettingsStore(),
        RecordSearchUseCase(InMemoryUserRepository()),
        documents_for_places=DocumentsForPlacesUseCase(documents),
    )

    text = str(message.answers[0]["text"])
    assert "📁 Tex passport va CMR" in text


def category_repository(count: int = 16) -> InMemoryPlaceRepository:
    """One category, `count` places — more than fits on a page."""
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    for index in range(count):
        add.execute(
            user_id=42,
            name=f"Заправка {index:02d}",
            categories=(PlaceCategory.FUEL,),
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
        )
    return repository


async def test_a_full_category_offers_the_next_page() -> None:
    repository = category_repository()
    query = FakeCallbackQuery("find:category:fuel")

    await handle_category_browse(
        query,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=10)),
        count_places_by_category=CountPlacesByCategoryUseCase(repository),
    )

    keyboard = query.message.answers[0]["reply_markup"].inline_keyboard
    assert [button.text for button in keyboard[-1]] == ["➡️"]
    assert keyboard[-1][0].callback_data == "find:cat_page:fuel:1"


async def test_the_next_page_carries_the_places_the_first_left_out() -> None:
    from app.presentation.telegram.handlers.find_place import handle_category_page

    repository = category_repository()
    query = FakeCallbackQuery("find:cat_page:fuel:1")

    await handle_category_page(
        query,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=10)),
        count_places_by_category=CountPlacesByCategoryUseCase(repository),
    )

    # Six left of sixteen, numbered on from the ten already shown.
    edit = query.message.edits[0]
    assert "Заправка 15" in edit["text"]
    assert "Заправка 09" not in edit["text"]
    assert edit["reply_markup"].inline_keyboard[0][0].text == "11"


async def test_turning_the_page_edits_the_message_it_is_on() -> None:
    # A new message per page would bury the list under its own history.
    from app.presentation.telegram.handlers.find_place import handle_category_page

    repository = category_repository()
    query = FakeCallbackQuery("find:cat_page:fuel:1")

    await handle_category_page(
        query,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=10)),
        count_places_by_category=CountPlacesByCategoryUseCase(repository),
    )

    assert len(query.message.edits) == 1
    assert query.message.answers == []


async def test_a_category_that_fits_on_one_page_gets_no_arrows() -> None:
    repository = category_repository(count=3)
    query = FakeCallbackQuery("find:category:fuel")

    await handle_category_browse(
        query,
        find_places=FindPlacesUseCase(repository),
        user_settings=FixedSettingsStore(UserSettings(result_limit=10)),
        count_places_by_category=CountPlacesByCategoryUseCase(repository),
    )

    keyboard = query.message.answers[0]["reply_markup"].inline_keyboard
    assert all(
        button.callback_data.startswith("place:") for row in keyboard for button in row
    )
