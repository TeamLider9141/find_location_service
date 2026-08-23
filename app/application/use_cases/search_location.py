from app.application.query_normalization import build_search_query_candidates
from app.domain.entities.location import Location
from app.domain.interfaces.geocoding import GeocodingProvider


class SearchLocationUseCase:
    def __init__(self, geocoder: GeocodingProvider) -> None:
        self._geocoder = geocoder

    async def execute(self, query: str, limit: int = 5) -> list[Location]:
        candidates = build_search_query_candidates(query)
        if not candidates:
            raise ValueError("query must not be empty")

        for candidate in candidates:
            locations = await self._geocoder.search(candidate, limit=limit)
            if locations:
                return locations

        return []
