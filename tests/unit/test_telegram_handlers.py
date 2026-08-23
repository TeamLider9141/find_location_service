from app.domain.entities.location import Location
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.handlers.location import (
    handle_location_selection,
    handle_nearby_category_selection,
    handle_realtime_nearby_start,
)
from app.presentation.telegram.handlers.search import (
    handle_add_location_menu,
    handle_location_query,
    handle_search_location_menu,
)
from app.presentation.telegram.keyboards.menu import ADD_LOCATION_BUTTON, SEARCH_LOCATION_BUTTON
from app.presentation.telegram.selection_store import InMemoryAddLocationFlowStore
from app.presentation.telegram.selection_store import InMemoryLocationSelectionStore
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str | None, user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str | None, user_id: int = 42) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(text=None, user_id=user_id)
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


class RecordingSearchUseCase:
    def __init__(self, locations: list[Location]) -> None:
        self.locations = locations
        self.calls: list[tuple[str, int]] = []

    async def execute(self, query: str, limit: int = 5) -> list[Location]:
        self.calls.append((query, limit))
        return self.locations


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


def _location(name: str) -> Location:
    return Location(
        id=f"osm:node:{name}",
        name=name,
        address="Московская область",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id=f"node:{name}",
    )


def _place(name: str) -> Place:
    return Place(
        id=f"osm:node:{name}",
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        address="Moscow",
        phone=None,
        distance_meters=250,
        source="osm",
        source_id=f"node:{name}",
    )


async def test_search_handler_sends_inline_location_results_and_stores_them() -> None:
    store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_search(user_id=42)
    use_case = RecordingSearchUseCase([_location("Аэропорт Домодедово")])
    message = FakeMessage("  Домодедово аэропорт  ")

    await handle_location_query(
        message,
        search_location=use_case,
        selection_store=store,
        add_location_flow=flow_store,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert use_case.calls == [("Домодедово аэропорт", 10)]
    assert "1. Аэропорт Домодедово" in str(message.answers[0]["text"])
    assert message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data == "location:0"
    assert store.get(user_id=42, index=0).name == "Аэропорт Домодедово"
    assert flow_store.is_waiting(user_id=42) is False


async def test_search_handler_reports_when_no_locations_found() -> None:
    store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_search(user_id=42)
    use_case = RecordingSearchUseCase([])
    message = FakeMessage("unknown place")

    await handle_location_query(
        message,
        search_location=use_case,
        selection_store=store,
        add_location_flow=flow_store,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert "topilmadi" in str(message.answers[0]["text"]).lower()


async def test_search_handler_requires_add_location_button_before_searching() -> None:
    store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    use_case = RecordingSearchUseCase([_location("Аэропорт Домодедово")])
    message = FakeMessage("Домодедово аэропорт")

    await handle_location_query(
        message,
        search_location=use_case,
        selection_store=store,
        add_location_flow=flow_store,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert use_case.calls == []
    assert "knopka" in str(message.answers[0]["text"]).lower()


async def test_search_handler_accepts_coordinate_link_as_direct_location() -> None:
    store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start(user_id=42)
    use_case = RecordingSearchUseCase([_location("Аэропорт Домодедово")])
    message = FakeMessage("https://www.google.com/maps/search/?api=1&query=55.7512,37.6184")

    await handle_location_query(
        message,
        search_location=use_case,
        selection_store=store,
        add_location_flow=flow_store,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert use_case.calls == []
    assert "kategoriya" in str(message.answers[0]["text"]).lower()
    assert message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith(
        "add_category:0:"
    )
    stored = store.get(user_id=42, index=0)
    assert stored is not None
    assert stored.name == "Linkdan yuborilgan lokatsiya"
    assert stored.coordinates.latitude == 55.7512
    assert stored.coordinates.longitude == 37.6184
    assert flow_store.is_waiting(user_id=42) is False


async def test_search_flow_treats_coordinate_link_as_search_text() -> None:
    store = InMemoryLocationSelectionStore()
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_search(user_id=42)
    use_case = RecordingSearchUseCase([_location("Link result")])
    message = FakeMessage("https://www.google.com/maps/search/?api=1&query=55.7512,37.6184")

    await handle_location_query(
        message,
        search_location=use_case,
        selection_store=store,
        add_location_flow=flow_store,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert use_case.calls == [
        ("https://www.google.com/maps/search/?api=1&query=55.7512,37.6184", 10)
    ]
    assert "1. Link result" in str(message.answers[0]["text"])
    assert "kategoriya" not in str(message.answers[0]["text"]).lower()


async def test_add_location_menu_button_starts_add_flow() -> None:
    flow_store = InMemoryAddLocationFlowStore()
    message = FakeMessage(ADD_LOCATION_BUTTON)

    await handle_add_location_menu(message, add_location_flow=flow_store)

    assert flow_store.is_waiting(user_id=42) is True
    assert flow_store.is_add_mode(user_id=42) is True
    answer_text = str(message.answers[0]["text"]).lower()
    assert "manzil nomi" in answer_text
    assert "link" in answer_text
    assert "/cancel" in answer_text


async def test_search_location_menu_button_starts_search_flow() -> None:
    flow_store = InMemoryAddLocationFlowStore()
    message = FakeMessage(SEARCH_LOCATION_BUTTON)

    await handle_search_location_menu(message, add_location_flow=flow_store)

    assert flow_store.is_waiting(user_id=42) is True
    assert flow_store.is_search_mode(user_id=42) is True
    answer_text = str(message.answers[0]["text"]).lower()
    assert "qidiriladigan manzil" in answer_text
    assert "link" not in answer_text
    assert "location" not in answer_text
    assert "venue" not in answer_text
    assert "/cancel" in answer_text


async def test_location_selection_handler_sends_selected_location_details() -> None:
    store = InMemoryLocationSelectionStore()
    store.save(user_id=42, locations=[_location("Аэропорт Домодедово")])
    callback = FakeCallbackQuery("location:0")

    await handle_location_selection(callback, selection_store=store)

    assert "Natija: 1" in str(callback.message.answers[0]["text"])
    assert "Аэропорт Домодедово" in str(callback.message.answers[0]["text"])
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data == "add_location:0"
    assert callback.alerts == [None]


async def test_nearby_category_selection_lists_places_around_selected_location() -> None:
    store = InMemoryLocationSelectionStore()
    location = _location("Аэропорт Домодедово")
    store.save(user_id=42, locations=[location])
    callback = FakeCallbackQuery(f"nearby:0:{PlaceCategory.FUEL.value}")
    use_case = RecordingNearbyPlacesUseCase([_place("Gazprom")])

    await handle_nearby_category_selection(
        callback,
        selection_store=store,
        nearby_places=use_case,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert use_case.calls == [(location.coordinates, PlaceCategory.FUEL, 10_000, 10)]
    assert "1. Gazprom" in str(callback.message.answers[0]["text"])
    assert callback.alerts == [None]


async def test_realtime_nearby_start_asks_for_category() -> None:
    callback = FakeCallbackQuery("nearby_realtime:start")

    await handle_realtime_nearby_start(callback)

    assert "kategoriya" in str(callback.message.answers[0]["text"]).lower()
    assert callback.message.answers[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith(
        "nearby_realtime:"
    )
    assert callback.alerts == [None]


async def test_location_selection_handler_rejects_invalid_callback_data() -> None:
    store = InMemoryLocationSelectionStore()
    callback = FakeCallbackQuery("location:bad")

    await handle_location_selection(callback, selection_store=store)

    assert callback.alerts == ["Tanlov eskirgan. Qayta qidirib ko'ring."]
