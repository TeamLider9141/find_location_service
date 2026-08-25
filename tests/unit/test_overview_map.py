import aiohttp

from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.maps.google_static import MARKER_LIMIT, GoogleStaticMapRenderer

POINTS = [
    Coordinates(latitude=41.311, longitude=69.279),
    Coordinates(latitude=40.936, longitude=68.766),
]


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

    image = await renderer.render(POINTS)

    assert image == b"png"
    url = renderer.requested[0]
    assert "41.31100,69.27900" in url
    assert "40.93600,68.76600" in url
    assert "center=" not in url
    assert "zoom=" not in url


async def test_too_many_dots_are_capped_not_refused() -> None:
    crowd = [Coordinates(latitude=41.0, longitude=69.0)] * (MARKER_LIMIT + 50)
    renderer = StubbedRenderer()

    await renderer.render(crowd)

    assert renderer.requested[0].count("41.00000,69.00000") == MARKER_LIMIT


async def test_no_points_means_no_request() -> None:
    renderer = StubbedRenderer()

    assert await renderer.render([]) is None
    assert renderer.requested == []


async def test_a_network_failure_is_none() -> None:
    renderer = StubbedRenderer(error=aiohttp.ClientError("boom"))

    assert await renderer.render(POINTS) is None


async def test_a_refused_request_is_none() -> None:
    renderer = StubbedRenderer(image=None)

    assert await renderer.render(POINTS) is None
