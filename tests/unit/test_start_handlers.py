from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.access import DecideAddAccessUseCase, HasAddAccessUseCase
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository
from app.presentation.telegram.handlers.start import handle_cancel, handle_start
from app.presentation.telegram.keyboards.menu import (
    ADD_DOCUMENT_BUTTON,
    ADMIN_BUTTON,
    SEARCH_BUTTON,
)
from app.presentation.telegram.states import AddPlace


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int = 42) -> None:
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


def access_check(approved_ids: tuple[int, ...] = ()) -> HasAddAccessUseCase:
    repository = InMemoryAddAccessRepository()
    for user_id in approved_ids:
        DecideAddAccessUseCase(repository).execute(user_id, allow=True)
    return HasAddAccessUseCase(repository)


def menu_labels(message: FakeMessage) -> list[str]:
    return [
        button.text
        for row in message.answers[0]["reply_markup"].keyboard
        for button in row
    ]


async def test_start_shows_the_main_menu() -> None:
    message = FakeMessage()

    await handle_start(message, make_state(), admin_ids=(), has_add_access=access_check())

    assert SEARCH_BUTTON in menu_labels(message)


async def test_start_drops_a_half_finished_flow() -> None:
    # /start is the way out of a stuck wizard. Leaving the old state behind
    # would send the next message back into the middle of the add-place flow.
    message = FakeMessage()
    state = make_state()
    await state.set_state(AddPlace.location)
    await state.update_data(name="Газпром")

    await handle_start(message, state, admin_ids=(), has_add_access=access_check())

    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_cancel_clears_any_pending_flow() -> None:
    message = FakeMessage()
    state = make_state()
    await state.set_state(AddPlace.note)
    await state.update_data(name="Газпром")

    await handle_cancel(message, state, admin_ids=(), has_add_access=access_check())

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert "bekor" in str(message.answers[0]["text"]).lower()


async def test_cancel_returns_the_main_menu() -> None:
    message = FakeMessage()

    await handle_cancel(message, make_state(), admin_ids=(), has_add_access=access_check())

    assert message.answers[0]["reply_markup"].keyboard[0][0].text == SEARCH_BUTTON


async def test_an_admin_sees_the_panel_button_on_start() -> None:
    message = FakeMessage(user_id=99)

    await handle_start(
        message, make_state(), admin_ids=(99,), has_add_access=access_check()
    )

    assert ADMIN_BUTTON in menu_labels(message)


async def test_an_ordinary_driver_never_sees_the_panel_button() -> None:
    message = FakeMessage(user_id=42)

    await handle_start(
        message, make_state(), admin_ids=(99,), has_add_access=access_check()
    )

    assert ADMIN_BUTTON not in menu_labels(message)


async def test_cancel_keeps_the_panel_button_for_an_admin() -> None:
    # Leaving a flow must not silently downgrade the admin's keyboard.
    message = FakeMessage(user_id=99)

    await handle_cancel(
        message, make_state(99), admin_ids=(99,), has_add_access=access_check()
    )

    assert ADMIN_BUTTON in menu_labels(message)


async def test_an_approved_driver_gets_the_document_button_on_start() -> None:
    message = FakeMessage(user_id=42)

    await handle_start(
        message, make_state(), admin_ids=(), has_add_access=access_check((42,))
    )

    assert ADD_DOCUMENT_BUTTON in menu_labels(message)


async def test_a_plain_driver_gets_no_document_button_on_start() -> None:
    message = FakeMessage(user_id=42)

    await handle_start(
        message, make_state(), admin_ids=(), has_add_access=access_check((7,))
    )

    assert ADD_DOCUMENT_BUTTON not in menu_labels(message)
