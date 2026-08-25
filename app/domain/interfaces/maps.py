from typing import Protocol

from app.domain.entities.place import Place


class OverviewMapRenderer(Protocol):
    """One picture of every place in the database, bounds fitted to the dots.

    The driver about to share their location deserves to know what the map
    even holds — a sketch says it faster than any sentence. Each category
    draws in its own style; the whole place goes in so the renderer can
    decide how.
    """

    async def render(self, places: list[Place]) -> bytes | None:
        """PNG bytes, or None when the picture cannot be drawn right now."""
