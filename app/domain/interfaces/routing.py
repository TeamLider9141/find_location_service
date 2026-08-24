from typing import Protocol

from app.domain.value_objects.coordinates import Coordinates


class RoadRouter(Protocol):
    """Road distances between one origin and several destinations.

    Straight-line distance misleads a driver: the place across the river is
    "500 m" away with the bridge fifteen kilometres upstream. Only a routing
    service knows the roads.
    """

    async def road_distances(
        self, origin: Coordinates, destinations: list[Coordinates]
    ) -> list[float] | None:
        """Metres by road, one per destination, in order — or None when the
        service could not answer. None means "fall back", never "no roads"."""
