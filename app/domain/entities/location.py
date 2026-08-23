from dataclasses import dataclass

from app.domain.value_objects.coordinates import Coordinates


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    address: str
    coordinates: Coordinates
    source: str
    source_id: str
