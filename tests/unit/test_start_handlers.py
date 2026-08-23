from app.domain.entities.location import Location
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.handlers.start import handle_cancel
from app.presentation.telegram.selection_store import (
    InMemoryAddLocationFlowStore,
    InMemoryLocationSelectionStore,
)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int = 42) -> None:
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


def _location() -> Location:
    return Location(
        id="osm:node:1",
        name="Stored",
        address="Moscow",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id="node:1",
    )


async def test_cancel_resets_add_flow_and_returns_main_menu() -> None:
    selection_store = InMemoryLocationSelectionStore()
    selection_store.save(user_id=42, locations=[_location()])
    add_location_flow = InMemoryAddLocationFlowStore()
    add_location_flow.start(user_id=42)
    message = FakeMessage()

    await handle_cancel(
        message,
        selection_store=selection_store,
        add_location_flow=add_location_flow,
    )

    assert add_location_flow.is_waiting(user_id=42) is False
    assert selection_store.get(user_id=42, index=0) is None
    assert "bekor qilindi" in str(message.answers[0]["text"]).lower()
    assert message.answers[0]["reply_markup"].keyboard[0][0].text == "🔎 Manzil qidirish"
