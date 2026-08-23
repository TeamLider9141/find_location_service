from typing import Protocol

from app.domain.value_objects.coordinates import Coordinates


class RoutingProvider(Protocol):
    async def route(self, origin: Coordinates, destination: Coordinates) -> object:
        """Future routing interface placeholder."""
