from collections.abc import Sequence
from typing import Any

import httpx

from app.domain.entities.location import Location
from app.domain.interfaces.geocoding import GeocodingProvider
from app.infrastructure.providers.osm.mapper import map_nominatim_location


class NominatimGeocodingProvider(GeocodingProvider):
    def __init__(
        self,
        *,
        base_url: str = "https://nominatim.openstreetmap.org",
        user_agent: str = "find-location-bot/0.1",
        client: httpx.AsyncClient | None = None,
        language: str = "ru",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._user_agent = user_agent
        self._language = language

    async def search(self, query: str, limit: int = 5) -> list[Location]:
        response = await self._client.get(
            "/search",
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": limit,
            },
            headers={
                "User-Agent": self._user_agent,
                "Accept-Language": self._language,
            },
        )
        response.raise_for_status()
        results = _expect_sequence(response.json())
        return [map_nominatim_location(item) for item in results]

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _expect_sequence(value: Any) -> Sequence[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("Nominatim search response must be a list")
    return value
