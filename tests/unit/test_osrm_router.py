import asyncio

import aiohttp

from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.routing.osrm import OsrmRouter

ORIGIN = Coordinates(latitude=55.75, longitude=37.61)
NEAR = Coordinates(latitude=55.76, longitude=37.62)
FAR = Coordinates(latitude=55.80, longitude=37.70)


class StubbedRouter(OsrmRouter):
    """The parser and URL under test, the network stubbed out."""

    def __init__(self, payload=None, error: Exception | None = None) -> None:
        super().__init__()
        self.requested: list[str] = []
        self._payload = payload
        self._error = error

    async def _fetch(self, url: str) -> dict:
        self.requested.append(url)
        if self._error is not None:
            raise self._error
        return self._payload


async def test_the_table_url_is_lon_lat_with_the_origin_first() -> None:
    router = StubbedRouter(payload={"code": "Ok", "distances": [[0, 1.0, 2.0]]})

    await router.road_distances(ORIGIN, [NEAR, FAR])

    url = router.requested[0]
    # OSRM wants lon,lat — the reverse of how coordinates are said aloud.
    assert "/table/v1/driving/37.61,55.75;37.62,55.76;37.7,55.8" in url
    assert "sources=0" in url
    assert "annotations=distance" in url


async def test_distances_come_back_in_destination_order() -> None:
    router = StubbedRouter(
        payload={"code": "Ok", "distances": [[0, 4200.0, 15300.0]]}
    )

    assert await router.road_distances(ORIGIN, [NEAR, FAR]) == [4200.0, 15300.0]


async def test_a_refusal_from_the_service_is_none() -> None:
    router = StubbedRouter(payload={"code": "NoTable", "message": "..."})

    assert await router.road_distances(ORIGIN, [NEAR]) is None


async def test_an_unroutable_destination_fails_the_whole_answer() -> None:
    # One null would misrank the rest; the honest straight line is better.
    router = StubbedRouter(payload={"code": "Ok", "distances": [[0, 4200.0, None]]})

    assert await router.road_distances(ORIGIN, [NEAR, FAR]) is None


async def test_a_network_failure_is_none_not_an_exception() -> None:
    router = StubbedRouter(error=aiohttp.ClientError("boom"))

    assert await router.road_distances(ORIGIN, [NEAR]) is None


async def test_a_timeout_is_none_not_an_exception() -> None:
    router = StubbedRouter(error=asyncio.TimeoutError())

    assert await router.road_distances(ORIGIN, [NEAR]) is None


async def test_no_destinations_needs_no_request() -> None:
    router = StubbedRouter(payload={"code": "Ok"})

    assert await router.road_distances(ORIGIN, []) == []
    assert router.requested == []
