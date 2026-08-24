import sqlite3
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.application.use_cases.admin import RecordUserVisitUseCase
from app.presentation.telegram.errors import report_service_error


class UserTrackingMiddleware(BaseMiddleware):
    """Record who sent each update, so the admin panel has users to report on."""

    def __init__(self, record_visit: RecordUserVisitUseCase) -> None:
        self._record_visit = record_visit

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender: User | None = data.get("event_from_user")
        if sender is not None:
            self._record(sender)

        return await handler(event, data)

    def _record(self, sender: User) -> None:
        # Tracking is bookkeeping around the driver's actual request. A locked
        # database must not cost them the answer they asked for.
        try:
            self._record_visit.execute(
                sender.id,
                full_name=sender.full_name or "",
                username=sender.username,
            )
        except sqlite3.Error as error:
            report_service_error(error, "record user visit")
