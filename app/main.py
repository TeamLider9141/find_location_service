import argparse
import asyncio
import sys

from app.config.settings import get_settings
from app.presentation.telegram.bot import (
    create_add_access_repository,
    create_bot,
    create_deletion_log,
    create_dispatcher,
    create_document_repository,
    create_overview_map,
    create_place_repository,
    create_road_router,
    create_throttle_middleware,
    create_user_repository,
    create_user_settings_store,
)
from app.presentation.telegram.commands import configure_commands
from app.presentation.telegram.database_backup import DatabaseBackup
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
        add_access=create_add_access_repository(settings),
        deletions=create_deletion_log(settings),
        documents_repository=create_document_repository(settings),
        admin_ids=settings.admin_ids,
        super_admin_ids=settings.super_admin_ids,
        road_router=create_road_router(settings),
        overview_map=create_overview_map(settings),
    )
    # The daily database copy to the supers — sent only when the file changed.
    backup = DatabaseBackup(bot, settings.database_path, settings.super_admin_ids)
    backup_task = asyncio.create_task(backup.run())
    try:
        await configure_commands(bot, settings.all_admin_ids)
        # Supers only: restarts are routine — deploys, cron — and the ordinary
        # rung can do nothing about them anyway.
        await announce_startup(bot, settings.super_admin_ids)
        await dispatcher.start_polling(bot)
    finally:
        backup_task.cancel()
        await bot.session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
