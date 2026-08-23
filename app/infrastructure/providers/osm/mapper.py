from typing import Any, Mapping

from app.domain.entities.location import Location
from app.domain.value_objects.coordinates import Coordinates


def map_nominatim_location(raw: Mapping[str, Any]) -> Location:
    osm_type = str(raw["osm_type"])
    osm_id = str(raw["osm_id"])
    display_name = str(raw["display_name"])
    name = str(raw.get("name") or display_name.split(",", maxsplit=1)[0]).strip()

    return Location(
        id=f"osm:{osm_type}:{osm_id}",
        name=name,
        address=display_name,
        coordinates=Coordinates(
            latitude=float(raw["lat"]),
            longitude=float(raw["lon"]),
        ),
        source="osm",
        source_id=f"{osm_type}:{osm_id}",
    )
