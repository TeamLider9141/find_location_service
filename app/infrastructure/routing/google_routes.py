"""Road distances from Google's Routes API (compute route matrix).

Better maps for this region than OSM, but metered: the free tier renews
monthly and every origin-destination pair is one billed element, so a search
with fifteen candidates spends fifteen. Every failure — quota, network, a pair
without a route — comes back as None so the caller can fall through to the
next router in the chain.
"""

import asyncio

import aiohttp

from app.domain.value_objects.coordinates import Coordinates

MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
REQUEST_TIMEOUT_SECONDS = 5.0


class GoogleRoutesRouter:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def road_distances(
        self, origin: Coordinates, destinations: list[Coordinates]
    ) -> list[float] | None:
        if not destinations:
            return []

        try:
            payload = await self._fetch(_matrix_body(origin, destinations))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

        return _parse_matrix(payload, expected=len(destinations))

    async def _fetch(self, body: dict) -> list:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        headers = {
            "X-Goog-Api-Key": self._api_key,
            # Without a field mask the API refuses the request outright.
            "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,condition",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(MATRIX_URL, json=body, headers=headers) as response:
                if response.status != 200:
                    return []
                return await response.json()


def _matrix_body(origin: Coordinates, destinations: list[Coordinates]) -> dict:
    return {
        "origins": [_waypoint(origin)],
        "destinations": [_waypoint(point) for point in destinations],
        "travelMode": "DRIVE",
    }


def _waypoint(point: Coordinates) -> dict:
    return {
        "waypoint": {
            "location": {
                "latLng": {
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                }
            }
        }
    }


def _parse_matrix(payload: object, expected: int) -> list[float] | None:
    if not isinstance(payload, list) or not payload:
        return None

    # Elements arrive in no promised order; the indexes say who is who.
    by_index: dict[int, float] = {}
    for element in payload:
        if element.get("condition") != "ROUTE_EXISTS":
            return None
        distance = element.get("distanceMeters")
        if distance is None:
            return None
        by_index[int(element.get("destinationIndex", -1))] = float(distance)

    if sorted(by_index) != list(range(expected)):
        # A missing or duplicated pair would silently misrank the rest; the
        # next router in the chain is the honest answer.
        return None

    return [by_index[index] for index in range(expected)]
