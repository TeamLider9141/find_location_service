from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from app.presentation.telegram.errors import report_service_error

PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Boshlash / menyu"),
    BotCommand(command="settings", description="Sozlamalar"),
    BotCommand(command="cancel", description="Jarayonni bekor qilish"),
]

ADMIN_COMMANDS = [*PUBLIC_COMMANDS, BotCommand(command="admin", description="Admin panel")]


async def configure_commands(bot: Bot, admin_ids: tuple[int, ...]) -> None:
    """Fill the Telegram menu button, once per startup.

    /admin goes out under a per-chat scope rather than the default one: the
    default list is what every driver sees, and a command they are refused has
    no place in it.
    """
    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())

    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as error:
            # Telegram rejects a chat scope for an admin who has never opened
            # the bot. They still reach the panel by typing the command.
            report_service_error(error, f"commands for admin {admin_id}")
