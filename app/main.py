import argparse
import asyncio
import sys

from app.config.settings import get_settings
from app.presentation.telegram.bot import (
    create_bot,
    create_dispatcher,
    create_place_repository,
    create_throttle_middleware,
    create_user_repository,
    create_user_settings_store,
)
from app.presentation.telegram.commands import configure_commands
from app.presentation.telegram.notifications import announce_startup
from app.shared.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shared places Telegram bot.")
    parser.parse_args(argv)

    configure_logging()
    return asyncio.run(run_bot())


async def run_bot() -> int:
    settings = get_settings()
    bot = create_bot(settings)
    dispatcher = create_dispatcher(
        create_place_repository(settings),
        users=create_user_repository(settings),
        user_settings=create_user_settings_store(settings),
        throttle=create_throttle_middleware(settings),
        admin_ids=settings.admin_ids,
    )
    try:
        await configure_commands(bot, settings.admin_ids)
        await announce_startup(bot, settings.admin_ids)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
