from app.domain.interfaces.routing import RoadRouter
from app.domain.value_objects.coordinates import Coordinates


class FirstAnsweringRouter:
    """Ask each router in turn; the first real answer wins.

    The order encodes preference — the better map first, the free fallback
    after it. All of them refusing is still None: the caller's straight-line
    fallback stays the last resort.
    """

    def __init__(self, routers: tuple[RoadRouter, ...]) -> None:
        self._routers = routers

    async def road_distances(
        self, origin: Coordinates, destinations: list[Coordinates]
    ) -> list[float] | None:
        for router in self._routers:
            distances = await router.road_distances(origin, destinations)
            if distances is not None:
                return distances
        return None
