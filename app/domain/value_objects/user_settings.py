from dataclasses import dataclass

RADIUS_STEP_METERS = 5_000
MIN_RADIUS_METERS = 5_000
MAX_RADIUS_METERS = 50_000

RESULT_LIMIT_STEP = 1
MIN_RESULT_LIMIT = 1
MAX_RESULT_LIMIT = 20


@dataclass(frozen=True)
class UserSettings:
    nearby_radius_meters: int = 10_000
    result_limit: int = 10
