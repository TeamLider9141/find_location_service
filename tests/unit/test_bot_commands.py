from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault

from app.presentation.telegram.commands import configure_commands


class FakeBot:
    def __init__(self, rejects: set[int] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._rejects = rejects or set()

    async def set_my_commands(self, commands, scope=None, **_: object) -> None:
        chat_id = getattr(scope, "chat_id", None)
        if chat_id in self._rejects:
            raise TelegramBadRequest(method=None, message="chat not found")

        self.calls.append({"commands": commands, "scope": scope})


def command_names(call: dict[str, object]) -> list[str]:
    return [command.command for command in call["commands"]]


async def test_every_driver_gets_the_public_commands() -> None:
    bot = FakeBot()

    await configure_commands(bot, admin_ids=())

    assert len(bot.calls) == 1
    assert isinstance(bot.calls[0]["scope"], BotCommandScopeDefault)
    assert command_names(bot.calls[0]) == ["start", "settings", "cancel"]


def test_admin_is_not_advertised_to_everyone() -> None:
    # The default scope is what a stranger sees in the menu button. A command
    # they cannot use has no business being listed there.
    from app.presentation.telegram.commands import PUBLIC_COMMANDS

    assert "admin" not in [command.command for command in PUBLIC_COMMANDS]


async def test_an_admin_gets_the_panel_command_in_their_own_chat() -> None:
    bot = FakeBot()

    await configure_commands(bot, admin_ids=(99,))

    admin_call = bot.calls[-1]
    assert isinstance(admin_call["scope"], BotCommandScopeChat)
    assert admin_call["scope"].chat_id == 99
    assert "admin" in command_names(admin_call)


async def test_an_admin_who_never_opened_the_bot_does_not_break_startup() -> None:
    # Telegram refuses a chat scope for someone who has not messaged the bot.
    # That must cost the other admins nothing.
    bot = FakeBot(rejects={99})

    await configure_commands(bot, admin_ids=(99, 100))

    assert [call["scope"].chat_id for call in bot.calls[1:]] == [100]
