import argparse
import asyncio
import sys

from app.config.settings import get_settings
from app.presentation.telegram.bot import (
    create_bot,
    create_dispatcher,
    create_place_repository,
)
from app.shared.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shared places Telegram bot.")
    parser.parse_args(argv)

    configure_logging()
    return asyncio.run(run_bot())


async def run_bot() -> int:
    settings = get_settings()
    bot = create_bot(settings)
    dispatcher = create_dispatcher(create_place_repository(settings))
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
