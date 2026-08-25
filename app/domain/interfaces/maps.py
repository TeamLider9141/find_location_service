from typing import Protocol

from app.domain.value_objects.coordinates import Coordinates


class OverviewMapRenderer(Protocol):
    """One picture of every place in the database, bounds fitted to the dots.

    The driver about to share their location deserves to know what the map
    even holds — a sketch says it faster than any sentence.
    """

    async def render(self, points: list[Coordinates]) -> bytes | None:
        """PNG bytes, or None when the picture cannot be drawn right now."""
