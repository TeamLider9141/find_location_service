from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")

    def distance_to(self, other: "Coordinates") -> float:
        earth_radius_meters = 6_371_000
        lat1 = radians(self.latitude)
        lat2 = radians(other.latitude)
        delta_lat = radians(other.latitude - self.latitude)
        delta_lon = radians(other.longitude - self.longitude)

        a = (
            sin(delta_lat / 2) ** 2
            + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
        )
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return earth_radius_meters * c
