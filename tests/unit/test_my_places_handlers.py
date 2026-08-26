import sqlite3

from app.application.use_cases.places import (
    AddPlaceUseCase,
    DeletePlaceUseCase,
    ListMyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_deletions import InMemoryDeletionLog
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.keyboards.places import BORDER_CATEGORIES, BORDER_GROUP_VALUE
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.presentation.telegram.states import EditPlace
from app.presentation.telegram.handlers.my_places import (
    INVALID_SELECTION_MESSAGE,
    NOT_YOURS_MESSAGE,
    handle_cancel_delete,
    handle_category_prompt,
    handle_confirm_delete,
    handle_delete_prompt,
    handle_clear_note,
    handle_move,
    handle_move_prompt,
    handle_my_places,
    handle_rename,
    handle_rename_prompt,
    handle_renote,
    handle_renote_prompt,
    handle_set_category,
)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.full_name = "Ali"
        self.username = None


class FakeMessage:
    def __init__(self, user_id: int = 42, text: str = "") -> None:
        self.from_user = FakeUser(user_id)
        self.text = text
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


class ExplodingRepository(InMemoryPlaceRepository):
    def list_by_author(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")

    def update(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")

    def delete(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")


def seeded():
    repository = InMemoryPlaceRepository()
    place = AddPlaceUseCase(repository).execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    return repository, place


async def test_my_places_lists_only_my_contributions() -> None:
    repository, _ = seeded()
    AddPlaceUseCase(repository).execute(
        user_id=7,
        name="Чужое",
        categories=(PlaceCategory.CAFE,),
        coordinates=Coordinates(latitude=55.76, longitude=37.62),
    )
    callback = FakeCallbackQuery("my_data:places", user_id=42)
    message = callback.message

    await handle_my_places(callback, list_my_places=ListMyPlacesUseCase(repository))

    text = str(message.answers[0]["text"])
    assert "Газпром" in text
    assert "Чужое" not in text


async def test_my_places_offers_actions_on_each_of_my_places() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery("my_data:places", user_id=42)
    message = callback.message

    await handle_my_places(callback, list_my_places=ListMyPlacesUseCase(repository))

    keyboard = message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callback_data == [
        f"my_place:rename:{place.id}",
        f"my_place:renote:{place.id}",
        f"my_place:move:{place.id}",
        f"my_place:category:{place.id}",
        f"my_place:delete:{place.id}",
    ]


async def test_my_places_sends_one_card_per_place() -> None:
    repository, _ = seeded()
    AddPlaceUseCase(repository).execute(
        user_id=42,
        name="Лукойл",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.76, longitude=37.62),
    )
    callback = FakeCallbackQuery("my_data:places", user_id=42)
    message = callback.message

    await handle_my_places(callback, list_my_places=ListMyPlacesUseCase(repository))

    # One card each: the action buttons target a single place, so two places
    # cannot share one message.
    assert len(message.answers) == 2


async def test_my_places_when_empty_explains_how_to_add() -> None:
    callback = FakeCallbackQuery("my_data:places", user_id=99)
    message = callback.message

    await handle_my_places(
        callback,
        list_my_places=ListMyPlacesUseCase(InMemoryPlaceRepository()),
    )

    assert "qo'sh" in str(message.answers[0]["text"]).lower()


async def test_a_database_failure_while_listing_tells_the_driver() -> None:
    callback = FakeCallbackQuery("my_data:places", user_id=42)
    message = callback.message

    await handle_my_places(
        callback,
        list_my_places=ListMyPlacesUseCase(ExplodingRepository()),
    )

    assert "baza" in str(message.answers[0]["text"]).lower()


async def test_category_prompt_offers_every_category_for_that_place() -> None:
    _, place = seeded()
    callback = FakeCallbackQuery(f"my_place:category:{place.id}", user_id=42)

    await handle_category_prompt(callback)

    keyboard = callback.message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    expected = []
    for category in PlaceCategory:
        if category in BORDER_CATEGORIES:
            continue
        if category is PlaceCategory.OTHER:
            expected.append(f"my_place:set_category:{place.id}:{BORDER_GROUP_VALUE}")
        expected.append(f"my_place:set_category:{place.id}:{category.value}")
    assert callback_data == expected


async def test_category_prompt_rejects_a_callback_that_is_not_an_id() -> None:
    callback = FakeCallbackQuery("my_place:category:abc", user_id=42)

    await handle_category_prompt(callback)

    assert callback.alerts[0] is not None
    assert callback.message.answers == []


async def test_set_category_updates_my_place() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:cafe", user_id=42
    )

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert repository.get(place.id).category is PlaceCategory.CAFE


async def test_set_category_shows_the_updated_card() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:cafe", user_id=42
    )

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    text = str(callback.message.answers[0]["text"])
    assert "☕" in text
    assert callback.alerts == [None]


async def test_set_category_keeps_the_name_and_the_note() -> None:
    # Only the category was chosen; passing anything else through would let a
    # category change silently blank a name other drivers search for.
    repository = InMemoryPlaceRepository()
    place = AddPlaceUseCase(repository).execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="M5, 120 км",
    )
    callback = FakeCallbackQuery(f"my_place:set_category:{place.id}:cafe", user_id=42)

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    stored = repository.get(place.id)
    assert stored.name == "Газпром"
    assert stored.note == "M5, 120 км"


async def test_set_category_on_someone_elses_place_is_refused() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:cafe", user_id=7
    )

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert repository.get(place.id).category is PlaceCategory.FUEL
    assert NOT_YOURS_MESSAGE in callback.alerts


async def test_set_category_rejects_an_unknown_category() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:spaceship", user_id=42
    )

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert repository.get(place.id).category is PlaceCategory.FUEL
    assert callback.alerts[0] is not None


async def test_set_category_refuses_an_id_no_button_could_have_sent() -> None:
    # "-5" parses as an integer, so without the digit guard it would reach the
    # repository. Forged callback data has to stop at the parser, not one layer
    # deeper, and the driver has to see the same refusal as for any other
    # unreadable selection.
    repository, _ = seeded()
    callback = FakeCallbackQuery("my_place:set_category:-5:cafe", user_id=42)

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert callback.alerts == [INVALID_SELECTION_MESSAGE]


async def test_a_database_failure_while_updating_tells_the_driver() -> None:
    repository = ExplodingRepository()
    callback = FakeCallbackQuery("my_place:set_category:1:cafe", user_id=42)

    await handle_set_category(
        callback,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert "baza" in str(callback.message.answers[0]["text"]).lower()


async def test_delete_prompt_asks_for_confirmation() -> None:
    _, place = seeded()
    callback = FakeCallbackQuery(f"my_place:delete:{place.id}", user_id=42)

    await handle_delete_prompt(callback)

    keyboard = callback.message.answers[0]["reply_markup"]
    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert f"my_place:confirm_delete:{place.id}" in callback_data


async def test_delete_prompt_deletes_nothing_by_itself() -> None:
    # The prompt is a question. A driver who ignores it keeps their place.
    repository, place = seeded()
    callback = FakeCallbackQuery(f"my_place:delete:{place.id}", user_id=42)

    await handle_delete_prompt(callback)

    assert repository.get(place.id) is not None


async def test_confirm_delete_removes_my_place() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=42)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository, InMemoryDeletionLog()),
    )

    assert repository.get(place.id) is None


async def test_confirm_delete_on_someone_elses_place_is_refused() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=7)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository, InMemoryDeletionLog()),
    )

    assert repository.get(place.id) is not None
    assert NOT_YOURS_MESSAGE in callback.alerts


async def test_confirm_delete_survives_a_message_too_old_to_answer() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:confirm_delete:{place.id}", user_id=42, with_message=False
    )

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository, InMemoryDeletionLog()),
    )

    # The guard runs before the delete, so nothing is removed behind a driver
    # who cannot be told about it.
    assert repository.get(place.id) is not None
    assert callback.alerts[0] is not None


async def test_a_database_failure_while_deleting_tells_the_driver() -> None:
    callback = FakeCallbackQuery("my_place:confirm_delete:1", user_id=42)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(ExplodingRepository(), InMemoryDeletionLog()),
    )

    assert "baza" in str(callback.message.answers[0]["text"]).lower()


async def test_cancel_delete_keeps_the_place_and_closes_the_spinner() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery("my_place:cancel_delete", user_id=42)

    await handle_cancel_delete(callback)

    assert repository.get(place.id) is not None
    assert callback.alerts == [None]
    assert callback.message.answers != []


async def test_cancel_delete_on_an_expired_message_still_closes_the_spinner() -> None:
    # Without this the driver is left with a button that spins forever.
    callback = FakeCallbackQuery("my_place:cancel_delete", with_message=False)

    await handle_cancel_delete(callback)

    assert callback.alerts == [None]


async def test_the_border_group_keeps_the_place_id() -> None:
    # The sub keyboard's callbacks still carry the place id, so the eventual
    # choice knows its target.
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:{BORDER_GROUP_VALUE}", user_id=42
    )

    await handle_set_category(callback, update_place=UpdatePlaceUseCase(repository))

    keyboard = callback.message.answers[0]["reply_markup"]
    data = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert data == [
        f"my_place:set_category:{place.id}:border_kz",
        f"my_place:set_category:{place.id}:border_ru",
    ]
    # Nothing was written: the group tap is navigation, not a choice.
    assert repository.get(place.id).category == PlaceCategory.FUEL


async def test_picking_a_border_updates_the_place() -> None:
    repository, place = seeded()
    callback = FakeCallbackQuery(
        f"my_place:set_category:{place.id}:border_kz", user_id=42
    )

    await handle_set_category(callback, update_place=UpdatePlaceUseCase(repository))

    assert repository.get(place.id).category == PlaceCategory.BORDER_KZ


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        self.sent.append((chat_id, text))


async def test_an_owners_delete_is_announced_to_the_supers() -> None:
    # Deleting your own place is a right, but a spree of it is how the shared
    # database emptied once; the supers hear about each one immediately.
    repository, place = seeded()
    bot = FakeBot()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=42)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository, InMemoryDeletionLog()),
        super_admin_ids=(1, 2),
        bot=bot,
    )

    assert [chat_id for chat_id, _ in bot.sent] == [1, 2]
    assert place.name in bot.sent[0][1]


async def test_a_refused_delete_is_not_announced() -> None:
    repository, place = seeded()
    bot = FakeBot()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=7)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository, InMemoryDeletionLog()),
        super_admin_ids=(1,),
        bot=bot,
    )

    assert bot.sent == []


async def test_a_super_deleting_their_own_place_hears_no_echo() -> None:
    repository, place = seeded()  # place belongs to user 42
    bot = FakeBot()
    callback = FakeCallbackQuery(f"my_place:confirm_delete:{place.id}", user_id=42)

    await handle_confirm_delete(
        callback,
        delete_place=DeletePlaceUseCase(repository, InMemoryDeletionLog()),
        super_admin_ids=(42,),
        bot=bot,
    )

    assert bot.sent == []


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


async def _edit_state(place_id: int, edit_state) -> FSMContext:
    state = make_state()
    await state.set_state(edit_state)
    await state.update_data(edit_place_id=place_id)
    return state


async def test_the_rename_prompt_remembers_which_place() -> None:
    state = make_state()
    callback = FakeCallbackQuery("my_place:rename:7", user_id=42)

    await handle_rename_prompt(callback, state)

    assert await state.get_state() == EditPlace.name.state
    assert (await state.get_data())["edit_place_id"] == 7
    assert "nomini" in str(callback.message.answers[0]["text"]).lower()


async def test_renaming_rewrites_the_card() -> None:
    repository, place = seeded()
    state = await _edit_state(place.id, EditPlace.name)
    message = FakeMessage(text="  Лукойл  ", user_id=42)

    await handle_rename(message, state, update_place=UpdatePlaceUseCase(repository))

    assert repository.get(place.id).name == "Лукойл"
    assert await state.get_state() is None
    text = str(message.answers[-1]["text"])
    assert "Yangilandi" in text
    assert "Лукойл" in text


async def test_a_blank_new_name_is_refused_and_the_flow_waits() -> None:
    repository, place = seeded()
    state = await _edit_state(place.id, EditPlace.name)
    message = FakeMessage(text="   ", user_id=42)

    await handle_rename(message, state, update_place=UpdatePlaceUseCase(repository))

    assert repository.get(place.id).name == "Газпром"
    assert await state.get_state() == EditPlace.name.state


async def test_a_stranger_cannot_rename_someone_elses_place() -> None:
    repository, place = seeded()  # belongs to 42
    state = make_state(user_id=7)
    await state.set_state(EditPlace.name)
    await state.update_data(edit_place_id=place.id)
    message = FakeMessage(text="Меники", user_id=7)

    await handle_rename(message, state, update_place=UpdatePlaceUseCase(repository))

    assert repository.get(place.id).name == "Газпром"
    assert NOT_YOURS_MESSAGE in str(message.answers[-1]["text"])


async def test_the_note_is_replaced() -> None:
    repository, place = seeded()
    state = await _edit_state(place.id, EditPlace.note)
    message = FakeMessage(text="M5, kechasi ochiq", user_id=42)

    await handle_renote(message, state, update_place=UpdatePlaceUseCase(repository))

    assert repository.get(place.id).note == "M5, kechasi ochiq"


async def test_skip_clears_the_note() -> None:
    # /skip clears: a blank note is a value here, not an omission.
    repository, place = seeded()
    UpdatePlaceUseCase(repository).execute(
        place_id=place.id, user_id=42, note="eski izoh"
    )
    state = await _edit_state(place.id, EditPlace.note)

    await handle_clear_note(
        FakeMessage(text="/skip", user_id=42),
        state,
        update_place=UpdatePlaceUseCase(repository),
    )

    assert repository.get(place.id).note == ""


async def test_the_location_moves_to_the_new_coordinates() -> None:
    repository, place = seeded()
    state = await _edit_state(place.id, EditPlace.location)
    message = FakeMessage(text="41.36, 69.28", user_id=42)
    message.location = None
    message.venue = None

    await handle_move(message, state, update_place=UpdatePlaceUseCase(repository))

    moved = repository.get(place.id)
    assert (moved.coordinates.latitude, moved.coordinates.longitude) == (41.36, 69.28)
    assert "41.36" in str(message.answers[-1]["text"])


async def test_a_short_link_moves_the_place_too() -> None:
    class FakeResolver:
        async def resolve(self, url: str) -> str:
            return "https://www.google.com/maps/place/X/data=!3d41.364!4d69.288"

    repository, place = seeded()
    state = await _edit_state(place.id, EditPlace.location)
    message = FakeMessage(text="https://maps.app.goo.gl/abc", user_id=42)
    message.location = None
    message.venue = None

    await handle_move(
        message,
        state,
        update_place=UpdatePlaceUseCase(repository),
        link_resolver=FakeResolver(),
    )

    moved = repository.get(place.id)
    assert (moved.coordinates.latitude, moved.coordinates.longitude) == (41.364, 69.288)


async def test_an_unreadable_location_keeps_the_flow_waiting() -> None:
    repository, place = seeded()
    state = await _edit_state(place.id, EditPlace.location)
    message = FakeMessage(text="не координаты", user_id=42)
    message.location = None
    message.venue = None

    await handle_move(message, state, update_place=UpdatePlaceUseCase(repository))

    assert await state.get_state() == EditPlace.location.state
    assert repository.get(place.id).coordinates.latitude == 55.75
