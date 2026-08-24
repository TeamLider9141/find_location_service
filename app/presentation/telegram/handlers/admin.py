import sqlite3

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.admin import (
    DeletePlaceAsAdminUseCase,
    GetAdminOverviewUseCase,
    GetUserDetailUseCase,
    ListBroadcastRecipientsUseCase,
    ListUsersPageUseCase,
    TopSearchesUseCase,
)
from app.presentation.telegram.admin_formatters import (
    format_admin_overview,
    format_broadcast_preview,
    format_broadcast_result,
    format_top_searches,
    format_user_detail,
    format_users_page,
)
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
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
TOP_SEARCHES_LIMIT = 10

_BROADCAST_TEXT_KEY = "broadcast_text"


@router.message(Command("admin"))
async def handle_admin_command(message: Message, admin_ids: tuple[int, ...]) -> None:
    if not _is_admin(message, admin_ids):
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
    list_users_page: ListUsersPageUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    page_number = _parse_int(callback_query.data, prefix="admin:users:")
    if page_number is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    try:
        page = list_users_page.execute(page=page_number, page_size=USERS_PAGE_SIZE)
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
    user_detail: GetUserDetailUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
    if message is None:
        return

    user_id = _parse_int(callback_query.data, prefix="admin:user:")
    if user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
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
        reply_markup=build_user_detail_keyboard(detail.places),
    )
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
) -> None:
    message = await _open(callback_query, admin_ids)
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
    delete_place_as_admin: DeletePlaceAsAdminUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
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


@router.callback_query(F.data == "admin:broadcast")
async def handle_broadcast_start(
    callback_query: CallbackQuery,
    state: FSMContext,
    admin_ids: tuple[int, ...],
) -> None:
    message = await _open(callback_query, admin_ids)
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
    if not _is_admin(message, admin_ids):
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
    broadcast_recipients: ListBroadcastRecipientsUseCase,
) -> None:
    message = await _open(callback_query, admin_ids)
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
        try:
            await bot.send_message(chat_id, text)
        except TelegramAPIError as error:
            # Blocked bots and deleted accounts are the normal case here. One
            # unreachable driver must not silence everyone after them.
            report_service_error(error, f"broadcast to {chat_id}")
            failed += 1
        else:
            sent += 1

    return sent, failed


async def _open(callback_query: CallbackQuery, admin_ids: tuple[int, ...]) -> Message | None:
    """Return the message to reply in, after checking the tapper is an admin.

    Every callback goes through here: the callback data is guessable, so the
    check cannot live only in the command that hands out the buttons.
    """
    if not _is_admin(callback_query, admin_ids):
        await callback_query.answer(NOT_ADMIN_MESSAGE)
        return None

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return None

    return message


def _is_admin(update: object, admin_ids: tuple[int, ...]) -> bool:
    user_id = user_id_of(update)
    return user_id is not None and user_id in admin_ids


def _parse_int(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None

    raw = data[len(prefix) :]
    return int(raw) if raw.isdigit() else None
