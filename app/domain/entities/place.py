from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


@dataclass(frozen=True)
class Place:
    """A place contributed by a driver and shared with every other driver.

    ``added_by_user_id`` is not an ownership fence for reading — anyone can look a
    place up. It only decides who may edit or delete it.
    """

    id: int
    added_by_user_id: int
    name: str
    category: PlaceCategory
    coordinates: Coordinates
    note: str
    created_at: datetime
