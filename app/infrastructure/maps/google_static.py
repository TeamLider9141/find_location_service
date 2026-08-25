"""The overview sketch, drawn by Google's Static Maps API.

Given only markers — no centre, no zoom — the API fits the frame to the
outermost dots by itself, which is exactly the "scaled to wherever the
places are" behaviour wanted here. Every failure is None: the caller sends
its text prompt without the picture and nobody waits on a broken image.

Each category draws with its own colour and letter, and a place wearing
several categories gets the one style no single category uses — a
fuel-station-and-canteen is its own kind of dot.
"""

import asyncio

import aiohttp

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory

STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
REQUEST_TIMEOUT_SECONDS = 5.0
# A URL only holds so much; past this many dots the sketch reads the same
# anyway.
MARKER_LIMIT = 200

# Letters are the category's initial (English enum names, so they stay unique);
# Google only accepts one character from A-Z0-9.
_CATEGORY_STYLES: dict[PlaceCategory, str] = {
    PlaceCategory.RESTAURANT: "color:orange|label:R",
    PlaceCategory.CAFE: "color:brown|label:C",
    PlaceCategory.FUEL: "color:red|label:F",
    PlaceCategory.HOTEL: "color:blue|label:H",
    PlaceCategory.PARKING: "color:gray|label:P",
    PlaceCategory.CAR_SERVICE: "color:black|label:S",
    PlaceCategory.MOSQUE: "color:green|label:M",
    PlaceCategory.BORDER_KZ: "color:yellow|label:K",
    PlaceCategory.BORDER_RU: "color:yellow|label:U",
    PlaceCategory.OTHER: "color:white|label:O",
}
_MULTI_CATEGORY_STYLE = "color:purple"
_FALLBACK_STYLE = "color:white|label:O"


class GoogleStaticMapRenderer:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def render(self, places: list[Place]) -> bytes | None:
        if not places:
            return None

        try:
            return await self._fetch(self._map_url(places[:MARKER_LIMIT]))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    def _map_url(self, places: list[Place]) -> str:
        # One markers parameter per style: Google styles a whole group at once,
        # so the dots arrive already sorted into their colours.
        groups: dict[str, list[str]] = {}
        for place in places:
            point = (
                f"{place.coordinates.latitude:.5f},{place.coordinates.longitude:.5f}"
            )
            groups.setdefault(_style_for(place), []).append(point)

        markers = "&".join(
            f"markers={style}|" + "|".join(points) for style, points in groups.items()
        )
        return (
            f"{STATIC_MAP_URL}?size=640x640&scale=2&maptype=roadmap"
            f"&{markers}&key={self._api_key}"
        )

    async def _fetch(self, url: str) -> bytes | None:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                return await response.read()


def _style_for(place: Place) -> str:
    if len(place.categories) > 1:
        return _MULTI_CATEGORY_STYLE
    return _CATEGORY_STYLES.get(place.category, _FALLBACK_STYLE)
