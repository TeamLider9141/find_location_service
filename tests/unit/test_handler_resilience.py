import httpx

from app.domain.entities.location import Location
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.errors import EXPIRED_MESSAGE, SERVICE_UNAVAILABLE_MESSAGE
from app.presentation.telegram.handlers.location import (
    handle_location_selection,
    handle_nearby_category_selection,
)
from app.presentation.telegram.handlers.saved_places import (
    handle_cancel_delete,
    handle_cancel_save,
)
from app.presentation.telegram.handlers.search import handle_location_query
from app.presentation.telegram.keyboards.categories import editable_categories
from app.presentation.telegram.selection_store import (
    InMemoryAddLocationFlowStore,
    InMemoryLocationSelectionStore,
    InMemoryUserSettingsStore,
)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str | None = None, user_id: int = 42) -> None:
        self.text = text
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


class FailingSearchUseCase:
    async def execute(self, query: str, limit: int = 5) -> list[Location]:
        raise httpx.ConnectTimeout("nominatim is down")


class FailingNearbyPlacesUseCase:
    async def execute(self, *args: object, **kwargs: object) -> list[object]:
        raise httpx.HTTPStatusError(
            "overpass is overloaded",
            request=httpx.Request("GET", "https://overpass-api.de/api/interpreter"),
            response=httpx.Response(504),
        )


def _location() -> Location:
    return Location(
        id="osm:way:123",
        name="Аэропорт Домодедово",
        address="Московская область",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id="way:123",
    )


async def test_cancel_save_confirms_and_closes_the_callback() -> None:
    callback = FakeCallbackQuery("cancel_save")

    await handle_cancel_save(callback)

    assert "bekor qilindi" in str(callback.message.answers[0]["text"]).lower()
    assert callback.alerts == [None]


async def test_cancel_delete_confirms_and_closes_the_callback() -> None:
    callback = FakeCallbackQuery("cancel_delete")

    await handle_cancel_delete(callback)

    assert "bekor qilindi" in str(callback.message.answers[0]["text"]).lower()
    assert callback.alerts == [None]


async def test_search_reports_service_failure_instead_of_raising() -> None:
    flow_store = InMemoryAddLocationFlowStore()
    flow_store.start_search(user_id=42)
    message = FakeMessage("Домодедово аэропорт")

    await handle_location_query(
        message,
        search_location=FailingSearchUseCase(),
        selection_store=InMemoryLocationSelectionStore(),
        add_location_flow=flow_store,
        user_settings=InMemoryUserSettingsStore(),
    )

    assert message.answers[0]["text"] == SERVICE_UNAVAILABLE_MESSAGE


async def test_nearby_search_reports_service_failure_instead_of_raising() -> None:
    store = InMemoryLocationSelectionStore()
    store.save(user_id=42, locations=[_location()])
    callback = FakeCallbackQuery(f"nearby:0:{PlaceCategory.FUEL.value}")

    await handle_nearby_category_selection(
        callback,
        selection_store=store,
        nearby_places=FailingNearbyPlacesUseCase(),
        user_settings=InMemoryUserSettingsStore(),
    )

    assert callback.message.answers[0]["text"] == SERVICE_UNAVAILABLE_MESSAGE
    assert callback.alerts == [None]


async def test_callback_on_expired_message_alerts_instead_of_crashing() -> None:
    store = InMemoryLocationSelectionStore()
    store.save(user_id=42, locations=[_location()])
    callback = FakeCallbackQuery("location:0", with_message=False)

    await handle_location_selection(callback, selection_store=store)

    assert callback.alerts == [EXPIRED_MESSAGE]


def test_cafe_is_offered_as_a_category() -> None:
    assert PlaceCategory.CAFE in editable_categories()
