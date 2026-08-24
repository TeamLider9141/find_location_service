from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import TelegramObject, User

from app.presentation.telegram.errors import report_service_error

THROTTLED_MESSAGE = "Juda tez yozayapsiz. Birozdan so'ng qayta urinib ko'ring."

# A driver tapping menu buttons produces short bursts, so the bucket starts full
# and refills at one message a second. Anything faster than that is not typing.
BURST_SIZE = 5
REFILL_PER_SECOND = 1.0

# Answering every dropped message would double the flood instead of stopping it.
WARNING_INTERVAL_SECONDS = 10.0

# Sweeping the whole dictionary on every update would make the cheap path the
# expensive one, so idle senders are collected on a timer instead.
IDLE_SECONDS = 300.0
PRUNE_INTERVAL_SECONDS = 60.0


@dataclass
class _Bucket:
    tokens: float
    last_seen: float
    last_warned: float = 0.0


class ThrottleMiddleware(BaseMiddleware):
    """Drop messages from a driver who sends them faster than a human types.

    Registered on messages only. Inline buttons are throttled by the speed of a
    thumb, and a refused tap would leave the driver's spinner unexplained.
    """

    def __init__(
        self,
        burst: int = BURST_SIZE,
        refill_per_second: float = REFILL_PER_SECOND,
        warning_seconds: float = WARNING_INTERVAL_SECONDS,
        idle_seconds: float = IDLE_SECONDS,
        prune_interval_seconds: float = PRUNE_INTERVAL_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._burst = float(burst)
        self._refill_per_second = refill_per_second
        self._warning_seconds = warning_seconds
        self._idle_seconds = idle_seconds
        self._prune_interval_seconds = prune_interval_seconds
        self._clock = clock
        self._buckets: dict[int, _Bucket] = {}
        self._last_prune = clock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender: User | None = data.get("event_from_user")
        if sender is None:
            return await handler(event, data)

        now = self._clock()
        self._prune(now)
        bucket = self._refilled(sender.id, now)

        if bucket.tokens < 1:
            await self._warn(event, bucket, now)
            return None

        bucket.tokens -= 1
        return await handler(event, data)

    def tracked_senders(self) -> int:
        return len(self._buckets)

    def _refilled(self, user_id: int, now: float) -> _Bucket:
        bucket = self._buckets.get(user_id)
        if bucket is None:
            bucket = _Bucket(tokens=self._burst, last_seen=now)
            self._buckets[user_id] = bucket
            return bucket

        earned = (now - bucket.last_seen) * self._refill_per_second
        bucket.tokens = min(self._burst, bucket.tokens + earned)
        bucket.last_seen = now
        return bucket

    async def _warn(self, event: TelegramObject, bucket: _Bucket, now: float) -> None:
        if bucket.last_warned and now - bucket.last_warned < self._warning_seconds:
            return

        bucket.last_warned = now
        try:
            await event.answer(THROTTLED_MESSAGE)
        except TelegramAPIError as error:
            # A driver who blocked the bot mid-flood is the normal case here.
            report_service_error(error, "throttle warning")

    def _prune(self, now: float) -> None:
        if now - self._last_prune < self._prune_interval_seconds:
            return

        self._last_prune = now
        self._buckets = {
            user_id: bucket
            for user_id, bucket in self._buckets.items()
            if now - bucket.last_seen < self._idle_seconds
        }
