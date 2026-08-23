from dataclasses import dataclass

from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


@dataclass(frozen=True)
class SavedPlace:
    id: int
    user_id: int
    name: str
    category: PlaceCategory
    coordinates: Coordinates
    address: str
    source: str
    source_id: str
