from app.application.use_cases.saved_places import (
    AddSavedPlaceUseCase,
    DeleteSavedPlaceUseCase,
    ListSavedPlacesUseCase,
    UpdateSavedPlaceCategoryUseCase,
)
from app.domain.entities.location import Location
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_saved_places import InMemorySavedPlaceRepository
from app.presentation.telegram.handlers.saved_places import (
    handle_add_category_selection,
    handle_add_location_request,
    handle_confirm_delete_saved_place,
    handle_confirm_save_place,
    handle_filter_saved_places_by_category,
    handle_list_saved_places,
    handle_location_message,
    handle_venue_message,
    handle_view_saved_place,
    handle_saved_place_category_request,
    handle_saved_place_delete_request,
    handle_update_category_selection,
)
from app.presentation.telegram.keyboards.menu import SAVED_LOCATIONS_BUTTON
from app.presentation.telegram.selection_store import (
    InMemoryAddLocationFlowStore,
    InMemoryLocationSelectionStore,
    InMemoryUserSettingsStore,
)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(
        self,
        user_id: int = 42,
        venue: object | None = None,
        location: object | None = None,
    ) -> None:
        self.answers: list[dict[str, object]] = []
        self.from_user = FakeUser(user_id)
        self.venue = venue
        self.location = location

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id)
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


def _location(name: str = "Аэропорт Домодедово") -> Location:
    return Location(
        id="osm:way:123",
        name=name,
        address="Московская область",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id="way:123",
    )


class FakeVenueLocation:
    latitude = 55.4087
    longitude = 37.9094


class FakeVenue:
    title = "Cafe Driver"
    address = "Moscow"
    location = FakeVenueLocation()
    foursquare_id = None
    google_place_id = None


class FakeSharedLocation:
    latitude = 55.7512
    longitude = 37.6184


class RecordingNearbyPlacesUseCase:
    def __init__(self, places: list[Place]) -> None:
        self.places = places
        self.calls: list[tuple[Coordinates, PlaceCategory, int, int]] = []

    async def execute(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        self.calls.append((coordinates, category, radius_meters, limit))
        return self.places


def _place(name: str = "Gazprom") -> Place:
    return Place(
        id="osm:node:1",
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        address="Moscow",
        phone=None,
        distance_meters=250,
        source="osm",
        source_id="node:1",
    )


async def test_add_location_request_asks_for_category() -> None:
    selection_store = InMemoryLocationSelectionStore()
    selection_store.save(user_id=42, locations=[_location()])
    callback = FakeCallbackQuery("add_location:0")

    await handle_add_location_request(callback, selection_store=selection_store)

    assert "kategoriya" in str(callback.message.answers[0]["text"]).lower()
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith(
        "add_category:0:"
    )


async def test_venue_message_asks_for_category_and_stores_location() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start(user_id=42)
    message = FakeMessage(venue=FakeVenue())

    await handle_venue_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
    )

    assert "kategoriya" in str(message.answers[0]["text"]).lower()
    assert message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith(
        "add_category:0:"
    )
    stored = selection_store.get(user_id=42, index=0)
    assert stored is not None
    assert stored.name == "Cafe Driver"
    assert stored.coordinates.latitude == 55.4087
    assert flow_store.is_waiting(user_id=42) is False


async def test_venue_message_requires_add_location_button_first() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    message = FakeMessage(venue=FakeVenue())

    await handle_venue_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
    )

    assert "knopka" in str(message.answers[0]["text"]).lower()
    assert selection_store.get(user_id=42, index=0) is None


async def test_venue_message_rejects_search_flow() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_search(user_id=42)
    message = FakeMessage(venue=FakeVenue())

    await handle_venue_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
    )

    assert "manzil qo'shish" in str(message.answers[0]["text"]).lower()
    assert selection_store.get(user_id=42, index=0) is None


async def test_location_message_asks_for_category_and_stores_location() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start(user_id=42)
    message = FakeMessage(location=FakeSharedLocation())

    await handle_location_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
    )

    assert "kategoriya" in str(message.answers[0]["text"]).lower()
    assert message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith(
        "add_category:0:"
    )
    stored = selection_store.get(user_id=42, index=0)
    assert stored is not None
    assert stored.name == "Telegram lokatsiya"
    assert stored.coordinates.latitude == 55.7512
    assert stored.coordinates.longitude == 37.6184
    assert flow_store.is_waiting(user_id=42) is False


async def test_location_message_requires_add_location_button_first() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    message = FakeMessage(location=FakeSharedLocation())

    await handle_location_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
    )

    assert "knopka" in str(message.answers[0]["text"]).lower()
    assert selection_store.get(user_id=42, index=0) is None


async def test_location_message_rejects_search_flow() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_search(user_id=42)
    message = FakeMessage(location=FakeSharedLocation())

    await handle_location_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
    )

    assert "manzil qo'shish" in str(message.answers[0]["text"]).lower()
    assert selection_store.get(user_id=42, index=0) is None


async def test_location_message_in_realtime_nearby_mode_lists_nearest_places() -> None:
    selection_store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_realtime_nearby(user_id=42, category=PlaceCategory.FUEL)
    nearby_places = RecordingNearbyPlacesUseCase([_place()])
    message = FakeMessage(location=FakeSharedLocation())

    await handle_location_message(
        message,
        selection_store=selection_store,
        add_location_flow=flow_store,
        nearby_places=nearby_places,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert nearby_places.calls == [
        (Coordinates(latitude=55.7512, longitude=37.6184), PlaceCategory.FUEL, 10_000, 10)
    ]
    assert "1. Gazprom" in str(message.answers[0]["text"])
    assert flow_store.is_waiting(user_id=42) is False


async def test_category_selection_asks_for_final_confirmation() -> None:
    selection_store = InMemoryLocationSelectionStore()
    selection_store.save(user_id=42, locations=[_location()])
    callback = FakeCallbackQuery(f"add_category:0:{PlaceCategory.FUEL.value}")

    await handle_add_category_selection(callback, selection_store=selection_store)

    answer = callback.message.answers[0]
    assert "tasdiqlaysizmi" in str(answer["text"]).lower()
    assert answer["reply_markup"].inline_keyboard[0][0].callback_data == "confirm_save:0:fuel"


async def test_confirm_save_persists_place_and_returns_management_buttons() -> None:
    selection_store = InMemoryLocationSelectionStore()
    selection_store.save(user_id=42, locations=[_location()])
    repository = InMemorySavedPlaceRepository()
    callback = FakeCallbackQuery(f"confirm_save:0:{PlaceCategory.FUEL.value}")

    await handle_confirm_save_place(
        callback,
        selection_store=selection_store,
        add_saved_place=AddSavedPlaceUseCase(repository),
    )

    saved = repository.get(user_id=42, saved_place_id=1)
    assert saved is not None
    assert saved.category == PlaceCategory.FUEL
    assert "saqlandi" in str(callback.message.answers[0]["text"]).lower()
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data == "saved_category:1"


async def test_saved_place_category_can_be_changed_inline() -> None:
    repository = InMemorySavedPlaceRepository()
    saved = AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location(),
        category=PlaceCategory.FUEL,
    )
    callback = FakeCallbackQuery(f"update_category:{saved.id}:{PlaceCategory.HOTEL.value}")

    await handle_update_category_selection(
        callback,
        update_saved_place_category=UpdateSavedPlaceCategoryUseCase(repository),
    )

    updated = repository.get(user_id=42, saved_place_id=saved.id)
    assert updated is not None
    assert updated.category == PlaceCategory.HOTEL
    assert "o'zgartirildi" in str(callback.message.answers[0]["text"]).lower()


async def test_saved_place_delete_requires_confirmation_then_deletes() -> None:
    repository = InMemorySavedPlaceRepository()
    saved = AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location(),
        category=PlaceCategory.FUEL,
    )
    request_callback = FakeCallbackQuery(f"saved_delete:{saved.id}")

    await handle_saved_place_delete_request(request_callback)

    assert "o'chirishni tasdiqlaysizmi" in str(request_callback.message.answers[0]["text"]).lower()
    assert request_callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data == (
        f"confirm_delete:{saved.id}"
    )

    confirm_callback = FakeCallbackQuery(f"confirm_delete:{saved.id}")
    await handle_confirm_delete_saved_place(
        confirm_callback,
        delete_saved_place=DeleteSavedPlaceUseCase(repository),
    )

    assert repository.get(user_id=42, saved_place_id=saved.id) is None
    assert "o'chirildi" in str(confirm_callback.message.answers[0]["text"]).lower()


async def test_saved_place_category_request_lists_update_options() -> None:
    callback = FakeCallbackQuery("saved_category:7")

    await handle_saved_place_category_request(callback)

    assert "yangi kategoriya" in str(callback.message.answers[0]["text"]).lower()
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith(
        "update_category:7:"
    )


async def test_saved_locations_button_lists_user_places() -> None:
    repository = InMemorySavedPlaceRepository()
    AddSavedPlaceUseCase(repository).execute(user_id=42, location=_location("Cafe Driver"), category=PlaceCategory.FUEL)
    AddSavedPlaceUseCase(repository).execute(user_id=42, location=_location("Hotel Road"), category=PlaceCategory.HOTEL)
    message = FakeMessage(venue=None)

    await handle_list_saved_places(message, list_saved_places=ListSavedPlacesUseCase(repository))

    assert "kategoriya" in str(message.answers[0]["text"]).lower()
    buttons = {
        row[0].callback_data: row[0].text
        for row in message.answers[0]["reply_markup"].inline_keyboard
    }
    assert buttons["saved_filter:fuel"] == "⛽ Gas quyish shaxobchasi"
    assert buttons["saved_filter:parking"] == "🅿️ Parking (bo'sh)"


async def test_saved_locations_button_reports_empty_list() -> None:
    repository = InMemorySavedPlaceRepository()
    message = FakeMessage(venue=None)

    await handle_list_saved_places(message, list_saved_places=ListSavedPlacesUseCase(repository))

    assert "kategoriya" in str(message.answers[0]["text"]).lower()
    assert all(
        "(bo'sh)" in row[0].text
        for row in message.answers[0]["reply_markup"].inline_keyboard
    )


async def test_saved_category_selection_lists_places_from_that_category() -> None:
    repository = InMemorySavedPlaceRepository()
    AddSavedPlaceUseCase(repository).execute(user_id=42, location=_location("Cafe Driver"), category=PlaceCategory.FUEL)
    AddSavedPlaceUseCase(repository).execute(user_id=42, location=_location("Hotel Road"), category=PlaceCategory.HOTEL)
    callback = FakeCallbackQuery("saved_filter:fuel")

    await handle_filter_saved_places_by_category(
        callback,
        list_saved_places=ListSavedPlacesUseCase(repository),
    )

    assert "⛽ Gas quyish shaxobchasi" in str(callback.message.answers[0]["text"])
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].text == "Cafe Driver"
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data == "saved_view:1"


async def test_empty_saved_category_selection_reports_empty_category() -> None:
    repository = InMemorySavedPlaceRepository()
    callback = FakeCallbackQuery("saved_filter:hotel")

    await handle_filter_saved_places_by_category(
        callback,
        list_saved_places=ListSavedPlacesUseCase(repository),
    )

    assert "bo'sh" in str(callback.message.answers[0]["text"]).lower()


async def test_saved_place_button_shows_saved_place_actions() -> None:
    repository = InMemorySavedPlaceRepository()
    saved = AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location("Cafe Driver"),
        category=PlaceCategory.FUEL,
    )
    callback = FakeCallbackQuery(f"saved_view:{saved.id}")

    await handle_view_saved_place(callback, list_saved_places=ListSavedPlacesUseCase(repository))

    assert "Cafe Driver" in str(callback.message.answers[0]["text"])
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data == f"saved_category:{saved.id}"
