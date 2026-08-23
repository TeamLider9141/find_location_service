import logging
from typing import Any

from aiogram.types import InaccessibleMessage

logger = logging.getLogger(__name__)

SERVICE_UNAVAILABLE_MESSAGE = "Xizmat hozir javob bermayapti. Birozdan so'ng qayta urinib ko'ring."
EXPIRED_MESSAGE = "Bu xabar eskirgan. Menyudan qaytadan boshlang."


def answerable_message(callback_query: Any) -> Any | None:
    """Return the message a callback query can reply to, or None when it is gone.

    Telegram drops the message body for buttons older than 48 hours, so
    ``callback_query.message`` is either missing or an ``InaccessibleMessage``.
    """
    message = getattr(callback_query, "message", None)
    if message is None or isinstance(message, InaccessibleMessage):
        return None
    return message


def user_id_of(update: Any) -> int | None:
    """Return the Telegram user id, or None for anonymous admins and channel posts."""
    user = getattr(update, "from_user", None)
    return None if user is None else user.id


def report_service_error(error: Exception, context: str) -> None:
    logger.warning("%s failed: %s", context, error)
