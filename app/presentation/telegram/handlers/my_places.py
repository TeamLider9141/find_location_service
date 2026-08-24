import sqlite3

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.places import (
    DeletePlaceUseCase,
    ListMyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import format_place_card
from app.presentation.telegram.keyboards.menu import MY_PLACES_BUTTON
from app.presentation.telegram.notifications import announce_owner_deletion
from app.presentation.telegram.keyboards.places import (
    BORDER_GROUP_VALUE,
    CHOOSE_BORDER_MESSAGE,
    build_border_choice_keyboard,
    build_my_place_actions_keyboard,
    build_place_delete_confirmation_keyboard,
    build_update_category_keyboard,
)

router = Router(name="my_places")

EMPTY_MESSAGE = (
    "Siz hali joy qo'shmagansiz.\n\n"
    "➕ Joy qo'shish orqali birinchi joyingizni qo'shing."
)
NOT_YOURS_MESSAGE = "Bu joyni faqat uni qo'shgan foydalanuvchi o'zgartira oladi."
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. 📒 Mening joylarim dan qaytadan oching."
DELETED_MESSAGE = "🗑 O'chirildi."
CANCELLED_MESSAGE = "O'chirish bekor qilindi."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."


@router.message(F.text == MY_PLACES_BUTTON)
async def handle_my_places(
    message: Message,
    list_my_places: ListMyPlacesUseCase,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    try:
        places = list_my_places.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "list my places")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    if not places:
        await message.answer(EMPTY_MESSAGE)
        return

    # One message per place: the action buttons under a card target a single
    # place, so two places cannot share one card without the buttons lying.
    for place in places:
        await message.answer(
            format_place_card(place),
            reply_markup=build_my_place_actions_keyboard(place.id),
        )


@router.callback_query(F.data.startswith("my_place:category:"))
async def handle_category_prompt(callback_query: CallbackQuery) -> None:
    place_id = _parse_id(callback_query.data, "my_place:category:")
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Yangi kategoriyani tanlang.",
        reply_markup=build_update_category_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:set_category:"))
async def handle_set_category(
    callback_query: CallbackQuery,
    update_place: UpdatePlaceUseCase,
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    # The borders hide behind one button; opening them keeps the place id in
    # the callbacks, so the eventual choice still knows its target.
    group_place_id = _parse_border_group(callback_query.data)
    if group_place_id is not None:
        await message.answer(
            CHOOSE_BORDER_MESSAGE,
            reply_markup=build_border_choice_keyboard(
                f"my_place:set_category:{group_place_id}"
            ),
        )
        await callback_query.answer()
        return

    parsed = _parse_id_and_category(callback_query.data)
    user_id = user_id_of(callback_query)
    if parsed is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    place_id, category = parsed
    try:
        place = update_place.execute(
            place_id=place_id,
            user_id=user_id,
            category=category,
        )
    except sqlite3.Error as error:
        report_service_error(error, "update place category")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    # The refusal comes from the update itself returning None rather than a
    # separate ownership read: one source of truth for who may edit, and no
    # window between the check and the write.
    if place is None:
        await callback_query.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(
        format_place_card(place),
        reply_markup=build_my_place_actions_keyboard(place.id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:delete:"))
async def handle_delete_prompt(callback_query: CallbackQuery) -> None:
    place_id = _parse_id(callback_query.data, "my_place:delete:")
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Bu joyni o'chirasizmi?",
        reply_markup=build_place_delete_confirmation_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:confirm_delete:"))
async def handle_confirm_delete(
    callback_query: CallbackQuery,
    delete_place: DeletePlaceUseCase,
    super_admin_ids: tuple[int, ...] = (),
    bot: Bot | None = None,
) -> None:
    place_id = _parse_id(callback_query.data, "my_place:confirm_delete:")
    user_id = user_id_of(callback_query)
    if place_id is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    # Guard before the delete, not after: a place removed behind a driver who
    # cannot be told about it is a silent loss of shared data.
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        deleted_place = delete_place.execute(place_id=place_id, user_id=user_id)
    except sqlite3.Error as error:
        report_service_error(error, "delete place")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if deleted_place is None:
        await callback_query.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(DELETED_MESSAGE)

    # Deleting your own place is a right, but a spree of it is how the shared
    # database emptied once — the supers hear about each one immediately. A
    # super deleting their own place is spared the echo of themselves.
    if bot is not None:
        sender = callback_query.from_user
        recipients = tuple(
            admin_id for admin_id in super_admin_ids if admin_id != user_id
        )
        await announce_owner_deletion(
            bot,
            recipients,
            full_name=(sender.full_name or "") if sender else "",
            username=sender.username if sender else None,
            user_id=user_id,
            place_name=deleted_place.name,
        )

    await callback_query.answer()


@router.callback_query(F.data == "my_place:cancel_delete")
async def handle_cancel_delete(callback_query: CallbackQuery) -> None:
    message = answerable_message(callback_query)
    if message is not None:
        await message.answer(CANCELLED_MESSAGE)

    # The spinner is closed even when the message is gone: an unanswered
    # callback spins on the driver's screen until Telegram times it out.
    await callback_query.answer()


def _parse_id(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    return int(raw) if raw.isdigit() else None


def _parse_id_and_category(data: str | None) -> tuple[int, PlaceCategory] | None:
    prefix = "my_place:set_category:"
    if data is None or not data.startswith(prefix):
        return None

    raw_id, _, raw_category = data.removeprefix(prefix).partition(":")
    if not raw_id.isdigit():
        return None
    try:
        return int(raw_id), PlaceCategory(raw_category)
    except ValueError:
        return None


def _parse_border_group(data: str | None) -> int | None:
    """The place id out of a border-group tap, or None for anything else."""
    prefix = "my_place:set_category:"
    if data is None or not data.startswith(prefix):
        return None

    raw_id, _, tail = data.removeprefix(prefix).partition(":")
    if tail == BORDER_GROUP_VALUE and raw_id.isdigit():
        return int(raw_id)
    return None
