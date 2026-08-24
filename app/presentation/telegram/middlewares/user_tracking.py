import sqlite3
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.application.use_cases.admin import RecordUserVisitUseCase
from app.presentation.telegram.errors import report_service_error
from app.presentation.telegram.notifications import announce_new_user


class UserTrackingMiddleware(BaseMiddleware):
    """Record who sent each update, so the admin panel has users to report on.

    A first-ever visit is also announced to the admins: a growing bot is the
    one thing the panel cannot show, because nobody opens it in time.
    """

    def __init__(
        self, record_visit: RecordUserVisitUseCase, admin_ids: tuple[int, ...] = ()
    ) -> None:
        self._record_visit = record_visit
        self._admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender: User | None = data.get("event_from_user")
        if sender is not None and self._record(sender):
            await self._announce(sender, data)

        return await handler(event, data)

    def _record(self, sender: User) -> bool:
        """Store the visit; True when this user was never seen before.

        Tracking is bookkeeping around the driver's actual request. A locked
        database must not cost them the answer they asked for — and if the
        write failed, "new" is unknown, so no announcement either.
        """
        try:
            return self._record_visit.execute(
                sender.id,
                full_name=sender.full_name or "",
                username=sender.username,
            )
        except sqlite3.Error as error:
            report_service_error(error, "record user visit")
            return False

    async def _announce(self, sender: User, data: dict[str, Any]) -> None:
        # An admin's own first visit is skipped: "new user: <the admin>",
        # delivered to that same admin, is noise not news.
        if sender.id in self._admin_ids:
            return

        bot = data.get("bot")
        if bot is None:
            return

        await announce_new_user(
            bot,
            self._admin_ids,
            full_name=sender.full_name or "",
            username=sender.username,
            user_id=sender.id,
        )
