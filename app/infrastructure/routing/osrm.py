"""Road distances from OSRM's table service.

One request answers every candidate at once: the origin is source 0, the
places are destinations, and the response carries a row of metres-by-road.
The public demo server offers no SLA, so every failure — timeout, HTTP error,
a response that is not "Ok" — comes back as None and the caller falls back to
straight-line distance rather than an error message.
"""

import asyncio

import aiohttp

from app.domain.value_objects.coordinates import Coordinates

DEFAULT_BASE_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT_SECONDS = 5.0


class OsrmRouter:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def road_distances(
        self, origin: Coordinates, destinations: list[Coordinates]
    ) -> list[float] | None:
        if not destinations:
            return []

        try:
            payload = await self._fetch(self._table_url(origin, destinations))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

        return _parse_distances(payload, expected=len(destinations))

    def _table_url(self, origin: Coordinates, destinations: list[Coordinates]) -> str:
        # OSRM wants lon,lat — the reverse of how everyone says coordinates
        # aloud, and exactly the mistake this helper exists to make once.
        points = ";".join(
            f"{point.longitude},{point.latitude}" for point in (origin, *destinations)
        )
        return (
            f"{self._base_url}/table/v1/driving/{points}"
            "?sources=0&annotations=distance"
        )

    async def _fetch(self, url: str) -> dict:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                return await response.json()


def _parse_distances(payload: dict, expected: int) -> list[float] | None:
    if payload.get("code") != "Ok":
        return None

    rows = payload.get("distances") or []
    if not rows:
        return None

    # Row 0 is "from the origin"; its first cell is origin-to-origin (zero) and
    # the rest line up with the destinations.
    row = rows[0][1:]
    if len(row) != expected or any(value is None for value in row):
        # A destination OSRM cannot snap to a road comes back as null. One
        # unroutable place must not pretend the others' numbers are wrong,
        # but a partial answer resorted by it would silently misrank — the
        # caller falls back to the honest straight line instead.
        return None

    return [float(value) for value in row]
