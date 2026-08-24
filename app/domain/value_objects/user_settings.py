from dataclasses import dataclass, replace

RADIUS_STEP_METERS = 5_000
MIN_RADIUS_METERS = 5_000
MAX_RADIUS_METERS = 50_000

RESULT_LIMIT_STEP = 1
MIN_RESULT_LIMIT = 1
MAX_RESULT_LIMIT = 20


@dataclass(frozen=True)
class UserSettings:
    # Wide by default: on an intercity highway the next place is rarely close,
    # and a driver who finds nothing blames the bot, not their radius setting.
    nearby_radius_meters: int = 50_000
    result_limit: int = 15

    # Stepping lives here, not in the stores: every store would otherwise carry
    # its own copy of the bounds, and two copies eventually disagree.
    def stepped_radius(self, steps: int) -> "UserSettings":
        radius = _clamp(
            self.nearby_radius_meters + steps * RADIUS_STEP_METERS,
            MIN_RADIUS_METERS,
            MAX_RADIUS_METERS,
        )
        return replace(self, nearby_radius_meters=radius)

    def stepped_result_limit(self, steps: int) -> "UserSettings":
        limit = _clamp(
            self.result_limit + steps * RESULT_LIMIT_STEP,
            MIN_RESULT_LIMIT,
            MAX_RESULT_LIMIT,
        )
        return replace(self, result_limit=limit)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
