"""The add-search-manage journey, run end to end over a real SQLite file.

The unit suite checks each handler against a fake repository. This walks the
same steps a driver walks in Telegram, in order, through one database — which is
where wiring mistakes live: a normalization rule that only works in the fake, a
place saved under a state the next handler never reads, a delete that leaves the
row searchable.
"""

import pytest

from app.application.use_cases.access import DecideAddAccessUseCase, RequestAddAccessUseCase
from app.application.use_cases.admin import RecordSearchUseCase
from app.application.use_cases.places import (
    AddPlaceUseCase,
    DeletePlaceUseCase,
    FindPlacesUseCase,
    ListMyPlacesUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.add_access import AddAccessStatus
from app.infrastructure.database.sqlite_add_access import SQLiteAddAccessRepository
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository
from app.infrastructure.database.sqlite_user_settings import SQLiteUserSettingsStore
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository
from app.presentation.telegram.handlers.add_place import (
    handle_add_place_start,
    handle_category,
    handle_duplicate_answer,
    handle_location,
    handle_name,
    handle_skip_note,
)
from app.presentation.telegram.handlers.find_place import (
    handle_nearby_location,
    handle_nearby_start,
    handle_text_query,
)
from app.presentation.telegram.handlers.admin import handle_allow_add
from app.presentation.telegram.handlers.my_places import handle_confirm_delete, handle_my_places
from app.presentation.telegram.handlers.settings import handle_settings_update
from app.presentation.telegram.handlers.start import handle_cancel
from app.presentation.telegram.states import AddPlace
from tests.integration.telegram_doubles import (
    FakeBot,
    FakeCallbackQuery,
    FakeLocationMessage,
    FakeMessage,
    make_state,
)

DRIVER = 42
OTHER_DRIVER = 7
ADMIN = 1
NEWCOMER = 99

# A fuel station on the M5 and a cafe eight kilometres up the road: far enough
# apart that a 5 km radius sees one of them and a 10 km radius sees both.
STATION = (55.7500, 37.6100)
CAFE = (55.8220, 37.6100)


class Journey:
    """One driver's session: the handlers, their dependencies, and their state."""

    def __init__(self, tmp_path) -> None:
        database = tmp_path / "journey.sqlite3"
        self.places = SQLitePlaceRepository(database)
        self.settings = SQLiteUserSettingsStore(database)
        self.access = SQLiteAddAccessRepository(database)
        self.request_add_access = RequestAddAccessUseCase(self.access)
        self.decide_add_access = DecideAddAccessUseCase(self.access)
        # The journey is about what approved drivers can do; the gate itself
        # has its own test below.
        for driver in (DRIVER, OTHER_DRIVER):
            self.access.set_status(driver, AddAccessStatus.APPROVED)
        self.add_place = AddPlaceUseCase(self.places)
        self.find_places = FindPlacesUseCase(self.places)
        self.nearby_places = NearbyPlacesUseCase(self.places)
        self.list_my_places = ListMyPlacesUseCase(self.places)
        self.delete_place = DeletePlaceUseCase(self.places)
        self.record_search = RecordSearchUseCase(InMemoryUserRepository())
        self.state = make_state(DRIVER)

    async def add(
        self,
        name: str,
        category: str,
        coordinates: tuple[float, float],
        user_id: int = DRIVER,
    ) -> FakeMessage:
        """Walk the whole add flow and return the message that closed it."""
        state = self.state if user_id == DRIVER else make_state(user_id)
        await handle_add_place_start(
            FakeMessage(user_id=user_id), state, self.request_add_access, admin_ids=()
        )
        await handle_name(FakeMessage(text=name, user_id=user_id), state)
        await handle_category(
            FakeCallbackQuery(f"add_place:category:{category}", user_id=user_id), state
        )
        location = FakeLocationMessage(*coordinates, user_id=user_id)
        await handle_location(location, state, self.add_place)

        if await state.get_state() == AddPlace.duplicate.state:
            return location

        note = FakeMessage(text="/skip", user_id=user_id)
        await handle_skip_note(note, state, self.add_place, ())
        return note

    async def search(self, query: str) -> FakeMessage:
        message = FakeMessage(text=query)
        await handle_text_query(message, self.find_places, self.settings, self.record_search)
        return message

    async def nearby(self, coordinates: tuple[float, float]) -> FakeMessage:
        await handle_nearby_start(FakeMessage(), self.state)
        message = FakeLocationMessage(*coordinates)
        await handle_nearby_location(message, self.state, self.nearby_places, self.settings)
        return message


def replies(message: FakeMessage) -> str:
    return "\n".join(str(answer["text"]) for answer in message.answers)


@pytest.fixture
def journey(tmp_path) -> Journey:
    return Journey(tmp_path)


async def test_a_saved_place_comes_back_with_a_map_link(journey: Journey) -> None:
    # Task 27 step 2: the add flow ends in a card the driver can navigate from.
    closing = await journey.add("Газпром", "fuel", STATION)

    text = replies(closing)
    assert "Saqlandi" in text
    assert "google.com/maps" in text


async def test_a_second_place_at_the_same_spot_is_questioned(journey: Journey) -> None:
    # Task 27 step 3: the warning names what it collided with, and nothing is
    # written until the driver answers.
    await journey.add("Газпром", "fuel", STATION)

    warned = await journey.add("Газпром 24", "fuel", STATION)

    assert "Газпром" in replies(warned)
    assert len(journey.list_my_places.execute(DRIVER)) == 1


async def test_refusing_the_duplicate_leaves_one_place(journey: Journey) -> None:
    await journey.add("Газпром", "fuel", STATION)
    await journey.add("Газпром 24", "fuel", STATION)

    await handle_duplicate_answer(FakeCallbackQuery("add_place:duplicate:no"), journey.state, ())

    assert [place.name for place in journey.list_my_places.execute(DRIVER)] == ["Газпром"]


async def test_confirming_the_duplicate_saves_both(journey: Journey) -> None:
    await journey.add("Газпром", "fuel", STATION)
    await journey.add("Газпром 24", "fuel", STATION)

    await handle_duplicate_answer(FakeCallbackQuery("add_place:duplicate:yes"), journey.state, ())
    # Consent only moves the flow on to the note step; the write happens there.
    await handle_skip_note(FakeMessage(text="/skip"), journey.state, journey.add_place, ())

    assert len(journey.list_my_places.execute(DRIVER)) == 2


async def test_a_latin_query_finds_a_cyrillic_place(journey: Journey) -> None:
    # Task 27 step 4: normalization has to survive the round trip through
    # SQLite, not only the in-memory repository.
    await journey.add("Газпром", "fuel", STATION)

    found = await journey.search("gazprom")

    assert "Газпром" in replies(found)


async def test_nearby_lists_what_is_inside_the_radius(journey: Journey) -> None:
    # Task 27 step 5, first half: the default 10 km radius covers both.
    await journey.add("Газпром", "fuel", STATION)
    await journey.add("Кафе М5", "cafe", CAFE)

    listed = replies(await journey.nearby(STATION))

    assert "Газпром" in listed
    assert "Кафе М5" in listed


async def test_narrowing_the_radius_drops_the_far_place(journey: Journey) -> None:
    # Task 27 step 5, second half: the settings a driver changed are the ones
    # the next search uses.
    await journey.add("Газпром", "fuel", STATION)
    await journey.add("Кафе М5", "cafe", CAFE)

    await handle_settings_update(FakeCallbackQuery("settings:radius:dec"), journey.settings)
    listed = replies(await journey.nearby(STATION))

    assert "Газпром" in listed
    assert "Кафе М5" not in listed


async def test_a_driver_only_manages_their_own_places(journey: Journey) -> None:
    # Task 27 step 6: reads are shared, writes are not.
    await journey.add("Газпром", "fuel", STATION)
    await journey.add("Кафе М5", "cafe", CAFE, user_id=OTHER_DRIVER)

    mine = FakeMessage()
    await handle_my_places(mine, journey.list_my_places)

    assert "Газпром" in replies(mine)
    assert "Кафе М5" not in replies(mine)


async def test_a_deleted_place_stops_being_searchable(journey: Journey) -> None:
    # Task 27 step 6: the row is gone, not merely hidden from its author.
    await journey.add("Газпром", "fuel", STATION)
    place_id = journey.list_my_places.execute(DRIVER)[0].id

    await handle_confirm_delete(
        FakeCallbackQuery(f"my_place:confirm_delete:{place_id}"), journey.delete_place
    )

    assert "Газпром" not in replies(await journey.search("gazprom"))


async def test_another_driver_cannot_delete_what_they_did_not_add(journey: Journey) -> None:
    await journey.add("Газпром", "fuel", STATION)
    place_id = journey.list_my_places.execute(DRIVER)[0].id

    await handle_confirm_delete(
        FakeCallbackQuery(f"my_place:confirm_delete:{place_id}", user_id=OTHER_DRIVER),
        journey.delete_place,
    )

    assert len(journey.list_my_places.execute(DRIVER)) == 1


async def test_cancelling_halfway_saves_nothing(journey: Journey) -> None:
    # Task 27 step 7: abandoned at the location step, the flow leaves no row
    # and no state behind.
    await handle_add_place_start(
        FakeMessage(), journey.state, journey.request_add_access, admin_ids=()
    )
    await handle_name(FakeMessage(text="Газпром"), journey.state)
    await handle_category(FakeCallbackQuery("add_place:category:fuel"), journey.state)

    await handle_cancel(FakeMessage(text="/cancel"), journey.state, ())

    assert await journey.state.get_state() is None
    assert journey.list_my_places.execute(DRIVER) == []


async def test_a_place_in_no_particular_category_is_still_findable(journey: Journey) -> None:
    # The fallback category has to survive the round trip like any other: it is
    # stored as a plain string, so a typo in the enum would only surface here.
    await journey.add("Bozor", "other", STATION)

    assert "Bozor" in replies(await journey.search("bozor"))


async def test_the_next_driver_finds_what_the_last_one_added(journey: Journey) -> None:
    # The point of the shared database: a place exists because somebody else
    # bothered to add it.
    await journey.add("Кафе М5", "cafe", CAFE, user_id=OTHER_DRIVER)

    assert "Кафе М5" in replies(await journey.search("kafe m5"))


async def test_adding_opens_only_after_the_admins_blessing(journey: Journey) -> None:
    # A stranger's first tap does not start the flow; it files a request.
    state = make_state(NEWCOMER)
    bot = FakeBot()
    first_try = FakeMessage(user_id=NEWCOMER)
    await handle_add_place_start(
        first_try, state, journey.request_add_access, admin_ids=(ADMIN,), bot=bot
    )

    assert await state.get_state() is None
    assert [chat_id for chat_id, _ in bot.sent] == [ADMIN]

    # The admin allows; the driver hears about it...
    await handle_allow_add(
        FakeCallbackQuery(f"admin:allow_add:{NEWCOMER}", user_id=ADMIN),
        (ADMIN,),
        journey.decide_add_access,
        bot,
    )
    assert bot.sent[-1][0] == NEWCOMER

    # ...and the same tap now opens the flow.
    second_try = FakeMessage(user_id=NEWCOMER)
    await handle_add_place_start(
        second_try, state, journey.request_add_access, admin_ids=(ADMIN,), bot=bot
    )
    assert await state.get_state() == AddPlace.name.state
