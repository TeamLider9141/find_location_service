from dataclasses import dataclass

from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    category: PlaceCategory
    coordinates: Coordinates
    address: str | None
    phone: str | None
    distance_meters: float | None
    source: str
    source_id: str
