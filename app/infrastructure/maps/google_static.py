"""The overview sketch, drawn by Google's Static Maps API.

Given only markers — no centre, no zoom — the API fits the frame to the
outermost dots by itself, which is exactly the "scaled to wherever the
places are" behaviour wanted here. Every failure is None: the caller sends
its text prompt without the picture and nobody waits on a broken image.
"""

import asyncio

import aiohttp

from app.domain.value_objects.coordinates import Coordinates

STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
REQUEST_TIMEOUT_SECONDS = 5.0
# A URL only holds so much; past this many dots the sketch reads the same
# anyway. The newest places win because the list arrives newest-capable.
MARKER_LIMIT = 200


class GoogleStaticMapRenderer:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def render(self, points: list[Coordinates]) -> bytes | None:
        if not points:
            return None

        try:
            return await self._fetch(self._map_url(points[:MARKER_LIMIT]))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    def _map_url(self, points: list[Coordinates]) -> str:
        dots = "|".join(f"{p.latitude:.5f},{p.longitude:.5f}" for p in points)
        return (
            f"{STATIC_MAP_URL}?size=640x640&scale=2&maptype=roadmap"
            f"&markers=color:red|size:small|{dots}"
            f"&key={self._api_key}"
        )

    async def _fetch(self, url: str) -> bytes | None:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                return await response.read()
