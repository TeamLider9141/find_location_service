from aiogram.exceptions import TelegramBadRequest

from app.presentation.telegram.notifications import STARTUP_MESSAGE, announce_startup


class FakeBot:
    def __init__(self, rejects: tuple[int, ...] = ()) -> None:
        self.sent: list[tuple[int, str]] = []
        self._rejects = rejects

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        if chat_id in self._rejects:
            raise TelegramBadRequest(method=None, message="chat not found")
        self.sent.append((chat_id, text))


async def test_every_admin_hears_about_the_restart() -> None:
    bot = FakeBot()

    await announce_startup(bot, (1, 2))

    assert bot.sent == [(1, STARTUP_MESSAGE), (2, STARTUP_MESSAGE)]


async def test_a_bot_without_admins_stays_quiet() -> None:
    bot = FakeBot()

    await announce_startup(bot, ())

    assert bot.sent == []


async def test_an_unreachable_admin_does_not_stop_startup() -> None:
    # Telegram refuses a chat the admin never opened. That is not a reason to
    # leave the bot unstarted, nor to skip the admins after them.
    bot = FakeBot(rejects=(1,))

    await announce_startup(bot, (1, 2))

    assert bot.sent == [(2, STARTUP_MESSAGE)]
