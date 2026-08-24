from app.presentation.telegram.middlewares.throttling import (
    BURST_SIZE,
    THROTTLED_MESSAGE,
    WARNING_INTERVAL_SECONDS,
    ThrottleMiddleware,
)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str, **_: object) -> None:
        self.answers.append(text)


class Handler:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, event: object, data: dict) -> str:
        self.calls += 1
        return "handled"


class Clock:
    """A hand-cranked clock. Sleeping through a rate limit test is not a test."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def middleware(clock: Clock) -> ThrottleMiddleware:
    return ThrottleMiddleware(clock=clock)


async def send(throttle: ThrottleMiddleware, handler: Handler, user_id: int = 42) -> FakeMessage:
    message = FakeMessage()
    await throttle(handler, message, {"event_from_user": FakeUser(user_id)})
    return message


async def test_a_single_message_goes_through() -> None:
    handler = Handler()

    await send(middleware(Clock()), handler)

    assert handler.calls == 1


async def test_a_normal_burst_goes_through() -> None:
    # Tapping menu buttons quickly is not flooding. The bucket has to absorb it.
    throttle, handler = middleware(Clock()), Handler()

    for _ in range(BURST_SIZE):
        await send(throttle, handler)

    assert handler.calls == BURST_SIZE


async def test_the_message_after_the_burst_is_dropped() -> None:
    throttle, handler = middleware(Clock()), Handler()

    for _ in range(BURST_SIZE + 1):
        await send(throttle, handler)

    assert handler.calls == BURST_SIZE


async def test_a_dropped_message_is_answered_once() -> None:
    throttle, handler = middleware(Clock()), Handler()
    for _ in range(BURST_SIZE):
        await send(throttle, handler)

    dropped = await send(throttle, handler)

    assert dropped.answers == [THROTTLED_MESSAGE]


async def test_a_flood_is_not_answered_every_time() -> None:
    # Answering each dropped message would turn one flood into two.
    throttle, handler = middleware(Clock()), Handler()
    for _ in range(BURST_SIZE):
        await send(throttle, handler)

    answered = [(await send(throttle, handler)).answers for _ in range(5)]

    assert answered == [[THROTTLED_MESSAGE], [], [], [], []]


async def test_the_warning_repeats_once_the_interval_passes() -> None:
    clock = Clock()
    throttle, handler = middleware(clock), Handler()
    for _ in range(BURST_SIZE + 1):
        await send(throttle, handler)

    clock.advance(WARNING_INTERVAL_SECONDS)
    for _ in range(BURST_SIZE + 1):
        dropped = await send(throttle, handler)

    assert dropped.answers == [THROTTLED_MESSAGE]


async def test_waiting_earns_the_right_to_send_again() -> None:
    clock = Clock()
    throttle, handler = middleware(clock), Handler()
    for _ in range(BURST_SIZE + 1):
        await send(throttle, handler)

    clock.advance(1.0)
    await send(throttle, handler)

    assert handler.calls == BURST_SIZE + 1


async def test_one_flooder_does_not_silence_everyone_else() -> None:
    throttle, handler = middleware(Clock()), Handler()
    for _ in range(BURST_SIZE + 3):
        await send(throttle, handler, user_id=1)

    await send(throttle, handler, user_id=2)

    assert handler.calls == BURST_SIZE + 1


async def test_an_update_without_a_sender_is_passed_through() -> None:
    # Channel posts carry no user, so there is nobody to rate limit.
    handler = Handler()

    result = await middleware(Clock())(handler, FakeMessage(), {})

    assert (handler.calls, result) == (1, "handled")


async def test_idle_senders_are_forgotten() -> None:
    # One entry per driver who ever wrote, kept forever, is a slow leak on a
    # bot that runs for months.
    clock = Clock()
    throttle, handler = middleware(clock), Handler()
    for user_id in range(50):
        await send(throttle, handler, user_id=user_id)

    clock.advance(3_600)
    await send(throttle, handler, user_id=999)

    assert throttle.tracked_senders() == 1


async def test_the_first_flood_is_answered_even_early_in_the_process() -> None:
    # monotonic() starts near zero on a freshly booted machine. Treating "never
    # warned" as a timestamp would swallow the warning for the first flood.
    clock = Clock()
    clock.now = 3.0
    throttle, handler = middleware(clock), Handler()
    for _ in range(BURST_SIZE):
        await send(throttle, handler)

    dropped = await send(throttle, handler)

    assert dropped.answers == [THROTTLED_MESSAGE]


async def test_the_burst_and_refill_are_configurable() -> None:
    clock = Clock()
    throttle = ThrottleMiddleware(burst=2, refill_per_second=0.5, clock=clock)
    handler = Handler()

    for _ in range(3):
        await send(throttle, handler)
    clock.advance(2.0)
    await send(throttle, handler)

    assert handler.calls == 3


async def test_a_zero_warning_interval_answers_every_dropped_message() -> None:
    throttle = ThrottleMiddleware(burst=1, warning_seconds=0, clock=Clock())
    handler = Handler()
    await send(throttle, handler)

    answered = [(await send(throttle, handler)).answers for _ in range(3)]

    assert answered == [[THROTTLED_MESSAGE]] * 3
