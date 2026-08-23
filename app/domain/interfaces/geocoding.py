from typing import Protocol

from app.domain.entities.location import Location


class GeocodingProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[Location]:
        """Search external geocoding data and return normalized locations."""
