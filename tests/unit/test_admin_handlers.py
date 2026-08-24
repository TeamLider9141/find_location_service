import sqlite3

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.access import DecideAddAccessUseCase, RevokeAddAccessUseCase
from app.application.use_cases.admin import (
    DeletePlaceAsAdminUseCase,
    GetAdminOverviewUseCase,
    GetUserDetailUseCase,
    ListBroadcastRecipientsUseCase,
    ListUsersPageUseCase,
    TopSearchesUseCase,
)
from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.domain.value_objects.add_access import AddAccessStatus
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository
from app.presentation.telegram.handlers import admin as admin_handlers
from app.presentation.telegram.handlers.admin import (
    ASK_BROADCAST_MESSAGE,
    BROADCAST_CANCELLED_MESSAGE,
    SEND_INTERVAL_SECONDS,
    DATABASE_ERROR_MESSAGE,
    DELETED_MESSAGE,
    INVALID_SELECTION_MESSAGE,
    NOT_ADMIN_MESSAGE,
    SUPER_ADMIN_ONLY_MESSAGE,
    UNKNOWN_USER_MESSAGE,
    handle_admin_command,
    handle_admin_home,
    handle_allow_add,
    handle_deny_add,
    handle_revoke_add,
    handle_admin_searches,
    handle_admin_stats,
    handle_admin_user_detail,
    handle_admin_users,
    handle_broadcast_cancel,
    handle_broadcast_send,
    handle_broadcast_start,
    handle_broadcast_text,
    handle_place_delete_cancel,
    handle_place_delete_confirm,
    handle_place_delete_prompt,
)
from app.presentation.telegram.states import AdminBroadcast

ADMIN_ID = 100
STRANGER_ID = 999
ADMIN_IDS = (ADMIN_ID,)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int = ADMIN_ID, text: str = "") -> None:
        self.from_user = FakeUser(user_id)
        self.text = text
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})

    @property
    def texts(self) -> list[str]:
        return [str(answer["text"]) for answer in self.answers]


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = ADMIN_ID, with_message: bool = True) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id) if with_message else None
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)

    @property
    def texts(self) -> list[str]:
        return [] if self.message is None else self.message.texts


class FakeBot:
    def __init__(
        self,
        blocked: set[int] | None = None,
        flood: dict[int, int] | None = None,
    ) -> None:
        self.sent: list[tuple[int, str]] = []
        self._blocked = blocked or set()
        # chat id -> how many more times sending to it hits flood control.
        self._flood = dict(flood or {})

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        if chat_id in self._blocked:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")

        remaining = self._flood.get(chat_id, 0)
        if remaining:
            self._flood[chat_id] = remaining - 1
            raise TelegramRetryAfter(method=None, message="flood control", retry_after=4)

        self.sent.append((chat_id, text))


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record what the broadcast waits for instead of actually waiting."""
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(admin_handlers.asyncio, "sleep", fake_sleep)
    return recorded


class ExplodingPlaces(InMemoryPlaceRepository):
    def count(self) -> int:
        raise sqlite3.OperationalError("database is locked")


def make_state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=ADMIN_ID, user_id=ADMIN_ID),
    )


@pytest.fixture
def places() -> InMemoryPlaceRepository:
    return InMemoryPlaceRepository()


@pytest.fixture
def users() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def seed_place(places, user_id: int = 7, name: str = "Газпром"):
    return AddPlaceUseCase(places).execute(
        user_id=user_id,
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )


# --- access control ---------------------------------------------------------


async def test_a_stranger_gets_no_panel(places, users) -> None:
    message = FakeMessage(user_id=STRANGER_ID)

    await handle_admin_command(message, admin_ids=ADMIN_IDS)

    assert message.texts == [NOT_ADMIN_MESSAGE]
    assert message.answers[0].get("reply_markup") is None


async def test_a_stranger_cannot_read_statistics(places, users) -> None:
    # The callback data is guessable, so every entry point checks, not just the
    # command that hands out the buttons.
    callback = FakeCallbackQuery("admin:stats", user_id=STRANGER_ID)

    await handle_admin_stats(
        callback,
        admin_ids=ADMIN_IDS,
        admin_overview=GetAdminOverviewUseCase(places, users),
    )

    assert callback.alerts == [NOT_ADMIN_MESSAGE]
    assert callback.texts == []


async def test_a_stranger_cannot_delete_a_place(places, users) -> None:
    stored = seed_place(places)
    callback = FakeCallbackQuery(
        f"admin:place_delete_confirm:{stored.id}", user_id=STRANGER_ID
    )

    await handle_place_delete_confirm(
        callback,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        delete_place_as_admin=DeletePlaceAsAdminUseCase(places),
    )

    assert places.get(stored.id) is not None


async def test_with_no_admin_configured_nobody_passes(places, users) -> None:
    message = FakeMessage(user_id=ADMIN_ID)

    await handle_admin_command(message, admin_ids=())

    assert message.texts == [NOT_ADMIN_MESSAGE]


# --- menu and sections ------------------------------------------------------


async def test_the_admin_gets_the_menu() -> None:
    message = FakeMessage()

    await handle_admin_command(message, admin_ids=ADMIN_IDS)

    assert message.answers[0]["reply_markup"] is not None


async def test_the_home_button_returns_the_menu() -> None:
    callback = FakeCallbackQuery("admin:home")

    await handle_admin_home(callback, admin_ids=ADMIN_IDS)

    assert callback.message.answers[0]["reply_markup"] is not None


async def test_statistics_report_the_database(places, users) -> None:
    seed_place(places)
    callback = FakeCallbackQuery("admin:stats")

    await handle_admin_stats(
        callback, admin_ids=ADMIN_IDS, admin_overview=GetAdminOverviewUseCase(places, users)
    )

    assert "Joylar: 1 ta" in callback.texts[0]


async def test_a_database_failure_is_answered_not_raised(places, users) -> None:
    callback = FakeCallbackQuery("admin:stats")

    await handle_admin_stats(
        callback,
        admin_ids=ADMIN_IDS,
        admin_overview=GetAdminOverviewUseCase(ExplodingPlaces(), users),
    )

    assert callback.texts == [DATABASE_ERROR_MESSAGE]


async def test_the_user_list_is_paged(places, users) -> None:
    for user_id in range(1, 8):
        users.record_seen(user_id, full_name=f"User {user_id}", username=None)
    callback = FakeCallbackQuery("admin:users:1")

    await handle_admin_users(
        callback, admin_ids=ADMIN_IDS, list_users_page=ListUsersPageUseCase(users, places)
    )

    assert "Sahifa 2" in callback.texts[0]


async def test_a_forged_page_number_is_refused(places, users) -> None:
    callback = FakeCallbackQuery("admin:users:abc")

    await handle_admin_users(
        callback, admin_ids=ADMIN_IDS, list_users_page=ListUsersPageUseCase(users, places)
    )

    assert callback.alerts == [INVALID_SELECTION_MESSAGE]


async def test_a_user_detail_shows_their_places(places, users) -> None:
    users.record_seen(7, full_name="Ali", username="ali")
    seed_place(places, user_id=7)
    callback = FakeCallbackQuery("admin:user:7")

    await handle_admin_user_detail(
        callback, admin_ids=ADMIN_IDS, user_detail=GetUserDetailUseCase(users, places)
    )

    assert "Газпром" in callback.texts[0]


async def test_an_unknown_user_is_reported(places, users) -> None:
    callback = FakeCallbackQuery("admin:user:404")

    await handle_admin_user_detail(
        callback, admin_ids=ADMIN_IDS, user_detail=GetUserDetailUseCase(users, places)
    )

    assert callback.alerts == [UNKNOWN_USER_MESSAGE]


async def test_top_searches_are_listed(places, users) -> None:
    users.record_search(1, "газпром")
    callback = FakeCallbackQuery("admin:searches")

    await handle_admin_searches(
        callback, admin_ids=ADMIN_IDS, top_searches=TopSearchesUseCase(users)
    )

    assert "газпром" in callback.texts[0]


# --- moderation -------------------------------------------------------------


async def test_delete_asks_before_removing(places, users) -> None:
    stored = seed_place(places)
    callback = FakeCallbackQuery(f"admin:place_delete:{stored.id}")

    await handle_place_delete_prompt(callback, admin_ids=ADMIN_IDS, super_admin_ids=ADMIN_IDS)

    assert places.get(stored.id) is not None
    assert callback.message.answers[0]["reply_markup"] is not None


async def test_confirming_removes_a_place_the_admin_never_added(places, users) -> None:
    stored = seed_place(places, user_id=7)
    callback = FakeCallbackQuery(f"admin:place_delete_confirm:{stored.id}")

    await handle_place_delete_confirm(
        callback,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        delete_place_as_admin=DeletePlaceAsAdminUseCase(places),
    )

    assert places.get(stored.id) is None
    assert DELETED_MESSAGE in callback.texts


async def test_deleting_a_place_that_is_already_gone_is_reported(places, users) -> None:
    callback = FakeCallbackQuery("admin:place_delete_confirm:404")

    await handle_place_delete_confirm(
        callback,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        delete_place_as_admin=DeletePlaceAsAdminUseCase(places),
    )

    assert callback.alerts == [INVALID_SELECTION_MESSAGE]


async def test_cancelling_keeps_the_place(places, users) -> None:
    stored = seed_place(places)
    callback = FakeCallbackQuery("admin:place_delete_cancel")

    await handle_place_delete_cancel(callback, admin_ids=ADMIN_IDS)

    assert places.get(stored.id) is not None


# --- broadcast --------------------------------------------------------------


async def test_broadcast_asks_for_the_text(places, users) -> None:
    state = make_state()
    callback = FakeCallbackQuery("admin:broadcast")

    await handle_broadcast_start(
        callback, state=state, admin_ids=ADMIN_IDS, super_admin_ids=ADMIN_IDS
    )

    assert await state.get_state() == AdminBroadcast.message.state
    assert ASK_BROADCAST_MESSAGE in callback.texts


async def test_the_typed_text_is_previewed_with_the_audience(places, users) -> None:
    state = make_state()
    await state.set_state(AdminBroadcast.message)
    users.record_seen(1, full_name="A", username=None)
    message = FakeMessage(text="Salom haydovchilar")

    await handle_broadcast_text(
        message,
        state=state,
        admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert "Salom haydovchilar" in message.texts[0]
    assert "1 ta" in message.texts[0]


async def test_sending_reaches_every_user(places, users) -> None:
    state = make_state()
    await state.update_data(broadcast_text="Salom")
    users.record_seen(1, full_name="A", username=None)
    users.record_seen(2, full_name="B", username=None)
    bot = FakeBot()
    callback = FakeCallbackQuery("admin:broadcast:send")

    await handle_broadcast_send(
        callback,
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert sorted(chat_id for chat_id, _ in bot.sent) == [1, 2]


async def test_a_blocked_user_does_not_stop_the_broadcast(places, users) -> None:
    # One driver blocking the bot must not silence the message for everyone
    # after them in the list.
    state = make_state()
    await state.update_data(broadcast_text="Salom")
    for user_id in (1, 2, 3):
        users.record_seen(user_id, full_name="U", username=None)
    bot = FakeBot(blocked={2})
    callback = FakeCallbackQuery("admin:broadcast:send")

    await handle_broadcast_send(
        callback,
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert sorted(chat_id for chat_id, _ in bot.sent) == [1, 3]
    assert "2 ta" in callback.texts[-1]
    assert "1 ta" in callback.texts[-1]


async def test_sending_without_a_pending_text_is_refused(places, users) -> None:
    state = make_state()
    bot = FakeBot()
    callback = FakeCallbackQuery("admin:broadcast:send")

    await handle_broadcast_send(
        callback,
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert bot.sent == []
    assert callback.alerts == [INVALID_SELECTION_MESSAGE]


async def test_the_pending_text_is_cleared_after_sending(places, users) -> None:
    # Otherwise a second confirmation tap would send the same message again.
    state = make_state()
    await state.update_data(broadcast_text="Salom")
    users.record_seen(1, full_name="A", username=None)
    bot = FakeBot()

    await handle_broadcast_send(
        FakeCallbackQuery("admin:broadcast:send"),
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )
    await handle_broadcast_send(
        FakeCallbackQuery("admin:broadcast:send"),
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert bot.sent == [(1, "Salom")]


async def test_cancelling_a_broadcast_sends_nothing(places, users) -> None:
    state = make_state()
    await state.set_state(AdminBroadcast.message)
    await state.update_data(broadcast_text="Salom")
    callback = FakeCallbackQuery("admin:broadcast:cancel")

    await handle_broadcast_cancel(callback, state=state, admin_ids=ADMIN_IDS)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert BROADCAST_CANCELLED_MESSAGE in callback.texts


async def test_an_expired_panel_message_does_not_crash(places, users) -> None:
    callback = FakeCallbackQuery("admin:home", with_message=False)

    await handle_admin_home(callback, admin_ids=ADMIN_IDS)

    assert callback.alerts != []


async def test_the_broadcast_paces_itself_between_sends(places, users, sleeps) -> None:
    # Telegram caps bots at about 30 messages a second. A tight loop over a few
    # hundred drivers earns a 429 partway through and loses the rest.
    state = make_state()
    await state.update_data(broadcast_text="Salom")
    for user_id in (1, 2, 3):
        users.record_seen(user_id, full_name="U", username=None)
    bot = FakeBot()

    await handle_broadcast_send(
        FakeCallbackQuery("admin:broadcast:send"),
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert sleeps == [SEND_INTERVAL_SECONDS] * 3


async def test_flood_control_is_waited_out_rather_than_counted_as_failed(
    places,
    users,
    sleeps,
) -> None:
    state = make_state()
    await state.update_data(broadcast_text="Salom")
    for user_id in (1, 2):
        users.record_seen(user_id, full_name="U", username=None)
    bot = FakeBot(flood={2: 1})
    callback = FakeCallbackQuery("admin:broadcast:send")

    await handle_broadcast_send(
        callback,
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert sorted(chat_id for chat_id, _ in bot.sent) == [1, 2]
    assert 4 in sleeps
    assert "Yetib bormadi: 0 ta" in callback.texts[-1]


async def test_a_second_flood_error_for_one_driver_gives_up(places, users, sleeps) -> None:
    # One retry, not a loop: a driver Telegram keeps refusing must not hold the
    # whole broadcast hostage.
    state = make_state()
    await state.update_data(broadcast_text="Salom")
    for user_id in (1, 2):
        users.record_seen(user_id, full_name="U", username=None)
    bot = FakeBot(flood={1: 5})
    callback = FakeCallbackQuery("admin:broadcast:send")

    await handle_broadcast_send(
        callback,
        state=state,
        bot=bot,
        admin_ids=ADMIN_IDS,
        super_admin_ids=ADMIN_IDS,
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
    )

    assert [chat_id for chat_id, _ in bot.sent] == [2]
    assert "Yetib bormadi: 1 ta" in callback.texts[-1]


def test_the_menu_button_opens_the_panel_too() -> None:
    # Two registrations for one callback: the /admin command and the reply
    # keyboard button an admin taps instead of typing it.
    registrations = [
        handler
        for handler in admin_handlers.router.message.handlers
        if handler.callback is handle_admin_command
    ]

    assert len(registrations) == 2


async def test_allowing_add_access_tells_the_driver() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.PENDING)
    bot = FakeBot()
    callback = FakeCallbackQuery("admin:allow_add:7")

    await handle_allow_add(callback, ADMIN_IDS, DecideAddAccessUseCase(access), bot)

    assert access.status(7) == AddAccessStatus.APPROVED
    assert bot.sent[0][0] == 7
    assert callback.alerts == [None]


async def test_refusing_add_access_tells_the_driver() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.PENDING)
    bot = FakeBot()
    callback = FakeCallbackQuery("admin:deny_add:7")

    await handle_deny_add(callback, ADMIN_IDS, DecideAddAccessUseCase(access), bot)

    assert access.status(7) == AddAccessStatus.REJECTED
    assert bot.sent[0][0] == 7


async def test_a_stranger_cannot_hand_out_add_access() -> None:
    # The callback data is guessable, so the check cannot live only in the
    # message that carries the buttons.
    access = InMemoryAddAccessRepository()
    callback = FakeCallbackQuery("admin:allow_add:7", user_id=STRANGER_ID)

    await handle_allow_add(callback, ADMIN_IDS, DecideAddAccessUseCase(access), FakeBot())

    assert access.status(7) is None
    assert callback.alerts == [NOT_ADMIN_MESSAGE]


async def test_a_blocked_driver_does_not_undo_the_decision() -> None:
    # The driver losing their own notification is their loss alone; the
    # decision still lands and the admin still hears it did.
    access = InMemoryAddAccessRepository()
    bot = FakeBot(blocked={7})
    callback = FakeCallbackQuery("admin:allow_add:7")

    await handle_allow_add(callback, ADMIN_IDS, DecideAddAccessUseCase(access), bot)

    assert access.status(7) == AddAccessStatus.APPROVED
    assert callback.alerts == [None]
    assert any("7" in text for text in callback.texts)


async def test_a_garbled_add_access_id_is_refused() -> None:
    access = InMemoryAddAccessRepository()
    callback = FakeCallbackQuery("admin:allow_add:abc")

    await handle_allow_add(callback, ADMIN_IDS, DecideAddAccessUseCase(access), FakeBot())

    assert callback.alerts == [INVALID_SELECTION_MESSAGE]


# --- the two admin rungs ----------------------------------------------------

ORDINARY_ADMIN_ID = 50
BOTH_RUNGS = (ORDINARY_ADMIN_ID, ADMIN_ID)


async def test_an_ordinary_admin_cannot_open_the_delete_prompt(places) -> None:
    # The panel looks identical on purpose; the refusal happens on the tap.
    stored = seed_place(places)
    callback = FakeCallbackQuery(f"admin:place_delete:{stored.id}", user_id=ORDINARY_ADMIN_ID)

    await handle_place_delete_prompt(
        callback, admin_ids=BOTH_RUNGS, super_admin_ids=ADMIN_IDS
    )

    assert callback.alerts == [SUPER_ADMIN_ONLY_MESSAGE]
    assert callback.texts == []


async def test_an_ordinary_admin_cannot_confirm_a_delete_either(places) -> None:
    # The confirm callback is guessable, so the prompt guard alone is not enough.
    stored = seed_place(places)
    callback = FakeCallbackQuery(
        f"admin:place_delete_confirm:{stored.id}", user_id=ORDINARY_ADMIN_ID
    )

    await handle_place_delete_confirm(
        callback,
        admin_ids=BOTH_RUNGS,
        super_admin_ids=ADMIN_IDS,
        delete_place_as_admin=DeletePlaceAsAdminUseCase(places),
    )

    assert places.get(stored.id) is not None
    assert callback.alerts == [SUPER_ADMIN_ONLY_MESSAGE]


async def test_an_ordinary_admin_cannot_start_a_broadcast() -> None:
    state = make_state()
    callback = FakeCallbackQuery("admin:broadcast", user_id=ORDINARY_ADMIN_ID)

    await handle_broadcast_start(
        callback, state=state, admin_ids=BOTH_RUNGS, super_admin_ids=ADMIN_IDS
    )

    assert callback.alerts == [SUPER_ADMIN_ONLY_MESSAGE]
    assert await state.get_state() is None


async def test_an_ordinary_admin_still_reads_statistics(places, users) -> None:
    seed_place(places)
    callback = FakeCallbackQuery("admin:stats", user_id=ORDINARY_ADMIN_ID)

    await handle_admin_stats(
        callback, admin_ids=BOTH_RUNGS, admin_overview=GetAdminOverviewUseCase(places, users)
    )

    assert "Joylar: 1 ta" in callback.texts[0]


async def test_an_ordinary_admin_can_hand_out_add_access() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.PENDING)
    callback = FakeCallbackQuery("admin:allow_add:7", user_id=ORDINARY_ADMIN_ID)

    await handle_allow_add(callback, BOTH_RUNGS, DecideAddAccessUseCase(access), FakeBot())

    assert access.status(7) == AddAccessStatus.APPROVED


# --- revoking add access ----------------------------------------------------


async def test_revoking_returns_the_driver_to_never_asked() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.APPROVED)
    bot = FakeBot()
    callback = FakeCallbackQuery("admin:revoke_add:7")

    await handle_revoke_add(callback, ADMIN_IDS, RevokeAddAccessUseCase(access), bot)

    assert access.status(7) is None
    assert bot.sent[0][0] == 7
    assert callback.alerts == [None]


async def test_an_ordinary_admin_can_revoke_too() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.APPROVED)
    callback = FakeCallbackQuery("admin:revoke_add:7", user_id=ORDINARY_ADMIN_ID)

    await handle_revoke_add(callback, BOTH_RUNGS, RevokeAddAccessUseCase(access), FakeBot())

    assert access.status(7) is None


async def test_a_stranger_cannot_revoke() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.APPROVED)
    callback = FakeCallbackQuery("admin:revoke_add:7", user_id=STRANGER_ID)

    await handle_revoke_add(callback, ADMIN_IDS, RevokeAddAccessUseCase(access), FakeBot())

    assert access.status(7) == AddAccessStatus.APPROVED
    assert callback.alerts == [NOT_ADMIN_MESSAGE]


async def test_a_blocked_driver_does_not_undo_the_revoke() -> None:
    access = InMemoryAddAccessRepository()
    access.set_status(7, AddAccessStatus.APPROVED)
    callback = FakeCallbackQuery("admin:revoke_add:7")

    await handle_revoke_add(
        callback, ADMIN_IDS, RevokeAddAccessUseCase(access), FakeBot(blocked={7})
    )

    assert access.status(7) is None
    assert callback.alerts == [None]
