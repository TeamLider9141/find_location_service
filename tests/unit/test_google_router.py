import aiohttp

from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.routing.chain import FirstAnsweringRouter
from app.infrastructure.routing.google_routes import GoogleRoutesRouter

ORIGIN = Coordinates(latitude=55.75, longitude=37.61)
NEAR = Coordinates(latitude=55.76, longitude=37.62)
FAR = Coordinates(latitude=55.80, longitude=37.70)


class StubbedGoogle(GoogleRoutesRouter):
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        super().__init__(api_key="test-key")
        self.bodies: list[dict] = []
        self._payload = payload
        self._error = error

    async def _fetch(self, body: dict) -> list:
        self.bodies.append(body)
        if self._error is not None:
            raise self._error
        return self._payload


async def test_the_matrix_body_carries_every_point_as_a_waypoint() -> None:
    router = StubbedGoogle(
        payload=[
            {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 1,
             "condition": "ROUTE_EXISTS"},
        ]
    )

    await router.road_distances(ORIGIN, [NEAR])

    body = router.bodies[0]
    assert body["travelMode"] == "DRIVE"
    assert len(body["origins"]) == 1
    assert body["destinations"][0]["waypoint"]["location"]["latLng"]["latitude"] == 55.76


async def test_elements_are_reassembled_by_destination_index() -> None:
    # The API promises no element order; only the indexes say who is who.
    router = StubbedGoogle(
        payload=[
            {"originIndex": 0, "destinationIndex": 1, "distanceMeters": 15300,
             "condition": "ROUTE_EXISTS"},
            {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 4200,
             "condition": "ROUTE_EXISTS"},
        ]
    )

    assert await router.road_distances(ORIGIN, [NEAR, FAR]) == [4200.0, 15300.0]


async def test_a_pair_without_a_route_fails_the_whole_answer() -> None:
    router = StubbedGoogle(
        payload=[
            {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 4200,
             "condition": "ROUTE_EXISTS"},
            {"originIndex": 0, "destinationIndex": 1, "condition": "ROUTE_NOT_FOUND"},
        ]
    )

    assert await router.road_distances(ORIGIN, [NEAR, FAR]) is None


async def test_a_refused_request_is_none_not_an_exception() -> None:
    # _fetch turns a non-200 into an empty list; quota exhaustion lands here.
    router = StubbedGoogle(payload=[])

    assert await router.road_distances(ORIGIN, [NEAR]) is None


async def test_a_network_failure_is_none() -> None:
    router = StubbedGoogle(error=aiohttp.ClientError("boom"))

    assert await router.road_distances(ORIGIN, [NEAR]) is None


class CannedRouter:
    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls = 0

    async def road_distances(self, origin, destinations):
        self.calls += 1
        return self.answer


async def test_the_chain_stops_at_the_first_answer() -> None:
    first = CannedRouter([100.0])
    second = CannedRouter([999.0])

    result = await FirstAnsweringRouter((first, second)).road_distances(ORIGIN, [NEAR])

    assert result == [100.0]
    assert second.calls == 0


async def test_the_chain_falls_through_a_refusal() -> None:
    first = CannedRouter(None)
    second = CannedRouter([999.0])

    result = await FirstAnsweringRouter((first, second)).road_distances(ORIGIN, [NEAR])

    assert result == [999.0]
    assert first.calls == 1


async def test_everyone_refusing_is_still_a_refusal() -> None:
    chain = FirstAnsweringRouter((CannedRouter(None), CannedRouter(None)))

    assert await chain.road_distances(ORIGIN, [NEAR]) is None
