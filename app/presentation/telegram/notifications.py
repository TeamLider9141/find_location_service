from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.presentation.telegram.errors import report_service_error

STARTUP_MESSAGE = "✅ Bot ishga tushdi."


async def announce_startup(bot: Bot, admin_ids: tuple[int, ...]) -> None:
    """Tell the admins the bot is up.

    A silent restart is indistinguishable from a crash that nobody noticed, and
    this is the only signal an admin gets without opening a server shell.
    """
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, STARTUP_MESSAGE)
        except TelegramAPIError as error:
            # An admin who has never opened the bot has no chat to write to.
            report_service_error(error, f"startup notice to admin {admin_id}")
