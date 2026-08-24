from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from app.presentation.telegram.errors import report_service_error
from app.presentation.telegram.keyboards.admin import build_add_access_keyboard

STARTUP_MESSAGE = "✅ Bot ishga tushdi."
NEW_USER_PREFIX = "🆕 Yangi foydalanuvchi"
ADD_REQUEST_PREFIX = "🙋 Joy qo'shishga ruxsat so'rayapti"


async def announce_startup(bot: Bot, admin_ids: tuple[int, ...]) -> None:
    """Tell the admins the bot is up.

    A silent restart is indistinguishable from a crash that nobody noticed, and
    this is the only signal an admin gets without opening a server shell.
    """
    await _tell_admins(bot, admin_ids, STARTUP_MESSAGE, context="startup notice")


async def announce_new_user(
    bot: Bot,
    admin_ids: tuple[int, ...],
    full_name: str,
    username: str | None,
    user_id: int,
) -> None:
    """Tell the admins somebody opened the bot for the first time."""
    await _tell_admins(
        bot,
        admin_ids,
        f"{NEW_USER_PREFIX}: {_label(full_name, username, user_id)}\nID: {user_id}",
        context="new user notice",
    )


async def announce_add_request(
    bot: Bot,
    admin_ids: tuple[int, ...],
    full_name: str,
    username: str | None,
    user_id: int,
) -> None:
    """Ask the admins to allow or refuse a driver who wants to add places."""
    await _tell_admins(
        bot,
        admin_ids,
        f"{ADD_REQUEST_PREFIX}: {_label(full_name, username, user_id)}\nID: {user_id}",
        context="add access request",
        reply_markup=build_add_access_keyboard(user_id),
    )


async def announce_add_verdict(
    bot: Bot,
    admin_ids: tuple[int, ...],
    full_name: str,
    username: str | None,
    decider_id: int,
    role: str,
    user_id: int,
    allow: bool,
) -> None:
    """Echo one admin's verdict to the rest, named and with their rung.

    Every admin held the same request buttons; without the echo the others
    would answer a request that is already settled.
    """
    decider = _label(full_name, username, decider_id)
    verdict = (
        f"✅ ID: {user_id} foydalanuvchini tasdiqladi"
        if allow
        else f"⛔ ID: {user_id} foydalanuvchining so'rovini rad etdi"
    )
    await _tell_admins(
        bot, admin_ids, f"ℹ️ {decider} ({role}) {verdict}.", context="add verdict echo"
    )


def _label(full_name: str, username: str | None, user_id: int) -> str:
    # Telegram accepts accounts whose visible name is blank. The id is the one
    # label that always exists, so the notice falls back to it.
    name = full_name or str(user_id)
    return f"{name} (@{username})" if username else name


async def _tell_admins(
    bot: Bot,
    admin_ids: tuple[int, ...],
    text: str,
    context: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except TelegramAPIError as error:
            # An admin who has never opened the bot has no chat to write to.
            report_service_error(error, f"{context} to admin {admin_id}")
