"""Following short map links to where the coordinates actually are.

A shared Google Maps link (maps.app.goo.gl/…) is a redirect with an opaque
token — the coordinates appear only in the URL it lands on. Resolution is one
GET with redirects followed; any failure is None, and the caller treats the
text as unreadable rather than erroring out.
"""

import asyncio
from urllib.parse import parse_qs, unquote, urlsplit

import aiohttp

REQUEST_TIMEOUT_SECONDS = 5.0


class HttpLinkResolver:
    def __init__(self, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    async def resolve(self, url: str) -> str | None:
        try:
            final = await self._final_url(url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

        return _unwrap_consent(final)

    async def _final_url(self, url: str) -> str:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=True, max_redirects=10) as response:
                return str(response.url)


def _unwrap_consent(url: str) -> str:
    # In some regions Google parks the redirect behind a consent wall and
    # tucks the real destination into ?continue=.
    if "consent." not in urlsplit(url).netloc:
        return url

    for value in parse_qs(urlsplit(url).query).get("continue", []):
        return unquote(value)
    return url
