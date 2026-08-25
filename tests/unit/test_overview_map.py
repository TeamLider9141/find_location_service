from datetime import datetime

import aiohttp

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.maps.google_static import MARKER_LIMIT, GoogleStaticMapRenderer


def make_place(
    latitude: float = 41.311,
    longitude: float = 69.279,
    categories: tuple[PlaceCategory, ...] = (PlaceCategory.FUEL,),
) -> Place:
    return Place(
        id=1,
        added_by_user_id=42,
        name="Joy",
        categories=categories,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        note="",
        created_at=datetime(2026, 1, 1),
    )


class StubbedRenderer(GoogleStaticMapRenderer):
    def __init__(self, image: bytes | None = b"png", error: Exception | None = None) -> None:
        super().__init__(api_key="test-key")
        self.requested: list[str] = []
        self._image = image
        self._error = error

    async def _fetch(self, url: str) -> bytes | None:
        self.requested.append(url)
        if self._error is not None:
            raise self._error
        return self._image


async def test_the_url_carries_every_dot_and_no_centre() -> None:
    # No centre and no zoom on purpose: given only markers the API fits the
    # frame to the outermost dots by itself.
    renderer = StubbedRenderer()

    image = await renderer.render(
        [make_place(41.311, 69.279), make_place(40.936, 68.766)]
    )

    assert image == b"png"
    url = renderer.requested[0]
    assert "41.31100,69.27900" in url
    assert "40.93600,68.76600" in url
    assert "center=" not in url
    assert "zoom=" not in url


async def test_each_category_draws_in_its_own_style() -> None:
    renderer = StubbedRenderer()

    await renderer.render(
        [
            make_place(41.1, 69.1, categories=(PlaceCategory.FUEL,)),
            make_place(41.2, 69.2, categories=(PlaceCategory.MOSQUE,)),
        ]
    )

    url = renderer.requested[0]
    assert "markers=color:red|label:F|41.10000,69.10000" in url
    assert "markers=color:green|label:M|41.20000,69.20000" in url


async def test_same_category_dots_share_one_marker_group() -> None:
    renderer = StubbedRenderer()

    await renderer.render(
        [
            make_place(41.1, 69.1, categories=(PlaceCategory.FUEL,)),
            make_place(41.2, 69.2, categories=(PlaceCategory.FUEL,)),
        ]
    )

    url = renderer.requested[0]
    assert url.count("markers=") == 1
    assert "41.10000,69.10000|41.20000,69.20000" in url


async def test_a_place_wearing_several_hats_gets_the_multi_style() -> None:
    # Purple belongs to no single category — a fuel-station-and-canteen is
    # its own kind of dot.
    renderer = StubbedRenderer()

    await renderer.render(
        [make_place(categories=(PlaceCategory.FUEL, PlaceCategory.RESTAURANT))]
    )

    url = renderer.requested[0]
    assert "markers=color:purple|41.31100,69.27900" in url
    assert "label:F" not in url


async def test_too_many_dots_are_capped_not_refused() -> None:
    crowd = [make_place(41.0, 69.0)] * (MARKER_LIMIT + 50)
    renderer = StubbedRenderer()

    await renderer.render(crowd)

    assert renderer.requested[0].count("41.00000,69.00000") == MARKER_LIMIT


async def test_no_points_means_no_request() -> None:
    renderer = StubbedRenderer()

    assert await renderer.render([]) is None
    assert renderer.requested == []


async def test_a_network_failure_is_none() -> None:
    renderer = StubbedRenderer(error=aiohttp.ClientError("boom"))

    assert await renderer.render([make_place()]) is None


async def test_a_refused_request_is_none() -> None:
    renderer = StubbedRenderer(image=None)

    assert await renderer.render([make_place()]) is None
