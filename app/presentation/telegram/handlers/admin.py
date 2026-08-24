import asyncio
import sqlite3

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.access import DecideAddAccessUseCase, RevokeAddAccessUseCase
from app.application.use_cases.admin import (
    AdminPlacesByCategoryUseCase,
    DeletePlaceAsAdminUseCase,
    GetAdminOverviewUseCase,
    GetUserDetailUseCase,
    ListBroadcastRecipientsUseCase,
    ListUsersPageUseCase,
    TopSearchesUseCase,
)
from app.application.use_cases.places import CountPlacesByCategoryUseCase
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.admin_formatters import (
    format_admin_overview,
    format_admin_places,
    format_broadcast_preview,
    format_broadcast_result,
    format_top_searches,
    format_user_detail,
    format_users_page,
)
from app.presentation.telegram.access import is_admin
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
)
from app.presentation.telegram.keyboards.admin import (
    USERS_PAGE_SIZE,
    build_admin_delete_confirmation_keyboard,
    build_admin_menu_keyboard,
    build_back_to_menu_keyboard,
    build_broadcast_confirmation_keyboard,
    build_user_detail_keyboard,
    build_users_page_keyboard,
)
from app.presentation.telegram.keyboards.menu import ADMIN_BUTTON
from app.presentation.telegram.keyboards.places import build_category_choice_keyboard
from app.presentation.telegram.notifications import announce_add_verdict
from app.presentation.telegram.states import AdminBroadcast

router = Router(name="admin")

MENU_MESSAGE = "🛠 Admin panel"
NOT_ADMIN_MESSAGE = "Bu bo'lim faqat admin uchun."
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. /admin dan qaytadan oching."
UNKNOWN_USER_MESSAGE = "Bunday foydalanuvchi topilmadi."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."
DELETED_MESSAGE = "🗑 Joy o'chirildi."
DELETE_CANCELLED_MESSAGE = "O'chirish bekor qilindi."
DELETE_PROMPT_MESSAGE = "Bu joyni bazadan butunlay o'chiraymi?"
ASK_BROADCAST_MESSAGE = "Yuboriladigan xabar matnini yozing. Bekor qilish uchun /cancel."
BROADCAST_CANCELLED_MESSAGE = "Xabar yuborish bekor qilindi."
ACCESS_GRANTED_MESSAGE = "✅ Ruxsat berildi"
ACCESS_DENIED_MESSAGE = "⛔ Rad etildi"
ACCESS_GRANTED_USER_MESSAGE = (
    "✅ Admin joy qo'shishga ruxsat berdi. ➕ Joy qo'shish tugmasini bosing."
)
ACCESS_DENIED_USER_MESSAGE = "⛔ Admin hozircha joy qo'shishga ruxsat bermadi."
CHOOSE_CATEGORY_MESSAGE = "Kategoriyani tanlang."
ACCESS_REVOKED_MESSAGE = "🚫 Ruxsat olib tashlandi"
ACCESS_REVOKED_USER_MESSAGE = "🚫 Admin joy qo'shish ruxsatingizni bekor qildi."
SUPER_ADMIN_ONLY_MESSAGE = "Bu faqat super admin uchun. Siz buni qila olmaysiz."
TOP_SEARCHES_LIMIT = 10
# ~20 messages a second, under Telegram's ~30/s ceiling for bots.
SEND_INTERVAL_SECONDS = 0.05

_BROADCAST_TEXT_KEY = "broadcast_text"


@router.message(Command("admin"))
@router.message(F.text == ADMIN_BUTTON)
async def handle_admin_command(message: Message, admin_ids: tuple[int, ...]) -> None:
    if not is_admin(message, admin_ids):
        await message.answer(NOT_ADMIN_MESSAGE)
        return

    await message.answer(MENU_MESSAGE, reply_markup=build_admin_menu_keyboard())


@router.callback_query(F.data == "admin:home")
async def handle_admin_home(callback_query: CallbackQuery, admin_ids: tuple[int, ...]) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    await message.answer(MENU_MESSAGE, reply_markup=build_admin_menu_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "admin:stats")
async def handle_admin_stats(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    admin_overview: GetAdminOverviewUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    try:
        overview = admin_overview.execute()
    except sqlite3.Error as error:
        report_service_error(error, "admin overview")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await message.answer(
        format_admin_overview(overview),
        reply_markup=build_back_to_menu_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:users:"))
async def handle_admin_users(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    list_users_page: ListUsersPageUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    page_number = _parse_int(callback_query.data, prefix="admin:users:")
    if page_number is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    hidden = _hidden_ids(callback_query, super_admin_ids)
    try:
        page = list_users_page.execute(
            page=page_number, page_size=USERS_PAGE_SIZE, exclude_ids=hidden
        )
    except sqlite3.Error as error:
        report_service_error(error, "admin user list")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await message.answer(format_users_page(page), reply_markup=build_users_page_keyboard(page))
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:user:"))
async def handle_admin_user_detail(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    user_detail: GetUserDetailUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    user_id = _parse_int(callback_query.data, prefix="admin:user:")
    if user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    # The list hides super admins from the ordinary rung, but the callback is
    # guessable, so the detail view checks again.
    if not _may_touch(callback_query, user_id, super_admin_ids):
        await callback_query.answer(SUPER_ADMIN_ONLY_MESSAGE, show_alert=True)
        return

    try:
        detail = user_detail.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "admin user detail")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if detail is None:
        await callback_query.answer(UNKNOWN_USER_MESSAGE)
        return

    await message.answer(
        format_user_detail(detail),
        reply_markup=build_user_detail_keyboard(detail.places, user_id=detail.user.id),
    )
    await callback_query.answer()


@router.callback_query(F.data == "admin:places")
async def handle_admin_places(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    count_places_by_category: CountPlacesByCategoryUseCase,
) -> None:
    """Open the location browser: the category keyboard, with counts."""
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    try:
        counts = count_places_by_category.execute(
            exclude_author_ids=_hidden_ids(callback_query, super_admin_ids)
        )
    except sqlite3.Error as error:
        report_service_error(error, "admin category counts")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await message.answer(
        CHOOSE_CATEGORY_MESSAGE,
        reply_markup=build_category_choice_keyboard("admin:places_cat", counts),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:places_cat:"))
async def handle_admin_places_category(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    admin_places_by_category: AdminPlacesByCategoryUseCase,
) -> None:
    """One category's places, grouped by the driver who added them."""
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    category = _parse_category(callback_query.data, prefix="admin:places_cat:")
    if category is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    try:
        groups = admin_places_by_category.execute(
            category, exclude_author_ids=_hidden_ids(callback_query, super_admin_ids)
        )
    except sqlite3.Error as error:
        report_service_error(error, "admin places by category")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await message.answer(format_admin_places(category, groups))
    await callback_query.answer()


@router.callback_query(F.data == "admin:searches")
async def handle_admin_searches(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    top_searches: TopSearchesUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    try:
        rows = top_searches.execute(limit=TOP_SEARCHES_LIMIT)
    except sqlite3.Error as error:
        report_service_error(error, "admin top searches")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await message.answer(format_top_searches(rows), reply_markup=build_back_to_menu_keyboard())
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:place_delete:"))
async def handle_place_delete_prompt(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
) -> None:
    message = await _open_super(callback_query, admin_ids, super_admin_ids)
    if message is None:
        return

    place_id = _parse_int(callback_query.data, prefix="admin:place_delete:")
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    await message.answer(
        DELETE_PROMPT_MESSAGE,
        reply_markup=build_admin_delete_confirmation_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:place_delete_confirm:"))
async def handle_place_delete_confirm(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    delete_place_as_admin: DeletePlaceAsAdminUseCase,
) -> None:
    message = await _open_super(callback_query, admin_ids, super_admin_ids)
    if message is None:
        return

    place_id = _parse_int(callback_query.data, prefix="admin:place_delete_confirm:")
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    try:
        deleted = delete_place_as_admin.execute(place_id)
    except sqlite3.Error as error:
        report_service_error(error, "admin delete place")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if not deleted:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    await message.answer(DELETED_MESSAGE)
    await callback_query.answer()


@router.callback_query(F.data == "admin:place_delete_cancel")
async def handle_place_delete_cancel(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    await message.answer(DELETE_CANCELLED_MESSAGE)
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:allow_add:"))
async def handle_allow_add(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    decide_add_access: DecideAddAccessUseCase,
    bot: Bot,
) -> None:
    await _decide_add_access(
        callback_query, admin_ids, super_admin_ids, decide_add_access, bot, allow=True
    )


@router.callback_query(F.data.startswith("admin:deny_add:"))
async def handle_deny_add(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    decide_add_access: DecideAddAccessUseCase,
    bot: Bot,
) -> None:
    await _decide_add_access(
        callback_query, admin_ids, super_admin_ids, decide_add_access, bot, allow=False
    )


async def _decide_add_access(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    decide_add_access: DecideAddAccessUseCase,
    bot: Bot,
    allow: bool,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    prefix = "admin:allow_add:" if allow else "admin:deny_add:"
    user_id = _parse_int(callback_query.data, prefix=prefix)
    if user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    if not _may_touch(callback_query, user_id, super_admin_ids):
        await callback_query.answer(SUPER_ADMIN_ONLY_MESSAGE, show_alert=True)
        return

    try:
        decide_add_access.execute(user_id, allow=allow)
    except sqlite3.Error as error:
        report_service_error(error, "add access decision")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    # The driver is waiting on this. A driver who blocked the bot in the
    # meantime loses only their own answer, not the admin's confirmation.
    verdict = ACCESS_GRANTED_USER_MESSAGE if allow else ACCESS_DENIED_USER_MESSAGE
    try:
        await bot.send_message(user_id, verdict)
    except TelegramAPIError as error:
        report_service_error(error, f"add access verdict to {user_id}")

    await _echo_verdict(callback_query, bot, admin_ids, super_admin_ids, user_id, allow)

    confirmation = ACCESS_GRANTED_MESSAGE if allow else ACCESS_DENIED_MESSAGE
    await message.answer(f"{confirmation} (ID: {user_id}).")
    await callback_query.answer()


async def _echo_verdict(
    callback_query: CallbackQuery,
    bot: Bot,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    user_id: int,
    allow: bool,
) -> None:
    """Tell the other admins who settled the request — not the decider, who
    just watched themselves do it."""
    decider = callback_query.from_user
    if decider is None:
        return

    role = "super admin" if is_admin(callback_query, super_admin_ids) else "admin"
    others = tuple(admin_id for admin_id in admin_ids if admin_id != decider.id)
    await announce_add_verdict(
        bot,
        others,
        full_name=decider.full_name or "",
        username=decider.username,
        decider_id=decider.id,
        role=role,
        user_id=user_id,
        allow=allow,
    )


@router.callback_query(F.data.startswith("admin:revoke_add:"))
async def handle_revoke_add(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    revoke_add_access: RevokeAddAccessUseCase,
    bot: Bot,
) -> None:
    """Take a driver's add permission back. Open to both admin rungs.

    The driver returns to the never-asked state, so their next attempt files
    a fresh request rather than hitting a standing refusal.
    """
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    user_id = _parse_int(callback_query.data, prefix="admin:revoke_add:")
    if user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    if not _may_touch(callback_query, user_id, super_admin_ids):
        await callback_query.answer(SUPER_ADMIN_ONLY_MESSAGE, show_alert=True)
        return

    try:
        revoke_add_access.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "add access revoke")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    # Told rather than left to find out: a driver whose next add silently asks
    # for permission again would file it as a bug.
    try:
        await bot.send_message(user_id, ACCESS_REVOKED_USER_MESSAGE)
    except TelegramAPIError as error:
        report_service_error(error, f"add access revoke notice to {user_id}")

    await message.answer(f"{ACCESS_REVOKED_MESSAGE} (ID: {user_id}).")
    await callback_query.answer()


@router.callback_query(F.data == "admin:broadcast")
async def handle_broadcast_start(
    callback_query: CallbackQuery,
    state: FSMContext,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
) -> None:
    message = await _open_super(callback_query, admin_ids, super_admin_ids)
    if message is None:
        return

    await state.set_state(AdminBroadcast.message)
    await message.answer(ASK_BROADCAST_MESSAGE)
    await callback_query.answer()


@router.message(AdminBroadcast.message, F.text)
async def handle_broadcast_text(
    message: Message,
    state: FSMContext,
    admin_ids: tuple[int, ...],
    broadcast_recipients: ListBroadcastRecipientsUseCase,
) -> None:
    if not is_admin(message, admin_ids):
        await state.clear()
        await message.answer(NOT_ADMIN_MESSAGE)
        return

    text = message.text or ""
    try:
        recipients = broadcast_recipients.execute()
    except sqlite3.Error as error:
        report_service_error(error, "broadcast recipients")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await state.update_data(**{_BROADCAST_TEXT_KEY: text})
    await message.answer(
        format_broadcast_preview(text, recipients=len(recipients)),
        reply_markup=build_broadcast_confirmation_keyboard(),
    )


@router.callback_query(F.data == "admin:broadcast:send")
async def handle_broadcast_send(
    callback_query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
    broadcast_recipients: ListBroadcastRecipientsUseCase,
) -> None:
    message = await _open_super(callback_query, admin_ids, super_admin_ids)
    if message is None:
        return

    data = await state.get_data()
    text = data.get(_BROADCAST_TEXT_KEY)
    if not text:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    # Clear before sending: a second tap on the same button would otherwise
    # deliver the message twice to everyone.
    await state.clear()

    try:
        recipients = broadcast_recipients.execute()
    except sqlite3.Error as error:
        report_service_error(error, "broadcast recipients")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    sent, failed = await _deliver(bot, recipients, text)
    await message.answer(
        format_broadcast_result(sent=sent, failed=failed),
        reply_markup=build_back_to_menu_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data == "admin:broadcast:cancel")
async def handle_broadcast_cancel(
    callback_query: CallbackQuery,
    state: FSMContext,
    admin_ids: tuple[int, ...],
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    await state.clear()
    await message.answer(BROADCAST_CANCELLED_MESSAGE)
    await callback_query.answer()


async def _deliver(bot: Bot, recipients: list[int], text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for chat_id in recipients:
        if await _send_one(bot, chat_id, text):
            sent += 1
        else:
            failed += 1

        # Telegram caps bots near 30 messages a second. Pacing the loop costs a
        # few seconds on a large list and avoids losing its tail to a 429.
        await asyncio.sleep(SEND_INTERVAL_SECONDS)

    return sent, failed


async def _send_one(bot: Bot, chat_id: int, text: str) -> bool:
    """Send to one driver, waiting out flood control once. True if delivered."""
    for attempt in range(2):
        try:
            await bot.send_message(chat_id, text)
        except TelegramRetryAfter as error:
            # Telegram says exactly how long to wait, so this one is worth
            # retrying — unlike a block, which will never succeed.
            report_service_error(error, f"broadcast to {chat_id}")
            if attempt == 0:
                await asyncio.sleep(error.retry_after)
                continue
            return False
        except TelegramAPIError as error:
            # Blocked bots and deleted accounts are the normal case here. One
            # unreachable driver must not silence everyone after them.
            report_service_error(error, f"broadcast to {chat_id}")
            return False
        else:
            return True

    return False


async def _open(callback_query: CallbackQuery, admin_ids: tuple[int, ...]) -> Message | None:
    """Return the message to reply in, after checking the tapper is an admin.

    Every callback goes through here: the callback data is guessable, so the
    check cannot live only in the command that hands out the buttons.
    """
    if not is_admin(callback_query, admin_ids):
        await callback_query.answer(NOT_ADMIN_MESSAGE)
        return None

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return None

    return message


def _may_touch(
    callback_query: CallbackQuery, target_id: int, super_admin_ids: tuple[int, ...]
) -> bool:
    """A super admin's row — their detail, their permissions — is off limits
    to the ordinary rung."""
    return target_id not in super_admin_ids or is_admin(callback_query, super_admin_ids)


def _hidden_ids(
    callback_query: CallbackQuery, super_admin_ids: tuple[int, ...]
) -> tuple[int, ...]:
    """What this viewer must not see: the ordinary rung is not shown the super
    admins — not their rows, not their places, not their counts."""
    return () if is_admin(callback_query, super_admin_ids) else super_admin_ids


def _parse_category(data: str | None, prefix: str) -> PlaceCategory | None:
    if data is None or not data.startswith(prefix):
        return None

    try:
        return PlaceCategory(data[len(prefix) :])
    except ValueError:
        return None


async def _open_super(
    callback_query: CallbackQuery,
    admin_ids: tuple[int, ...],
    super_admin_ids: tuple[int, ...],
) -> Message | None:
    """Like ``_open``, for the actions only a super admin may take.

    An ordinary admin sees the same buttons — the panel looks identical on
    purpose — so the refusal happens here, on the tap, as an alert.
    """
    message = await _open(callback_query, admin_ids)
    if message is None:
        return None

    if not is_admin(callback_query, super_admin_ids):
        await callback_query.answer(SUPER_ADMIN_ONLY_MESSAGE, show_alert=True)
        return None

    return message


def _parse_int(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None

    raw = data[len(prefix) :]
    return int(raw) if raw.isdigit() else None
