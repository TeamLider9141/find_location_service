"""Following short map links to where the coordinates actually are.

A shared Google Maps link (maps.app.goo.gl/…) is a redirect with an opaque
token — the coordinates appear only in the URL it lands on. Resolution is one
GET with redirects followed; any failure is None, and the caller treats the
text as unreadable rather than erroring out.
"""

import asyncio
import re
import ssl
from urllib.parse import parse_qs, unquote, urlsplit

import aiohttp

REQUEST_TIMEOUT_SECONDS = 5.0

# The point a Yandex organisation page draws for the place itself, written
# lon,lat in the page body — the URL of such a page names no coordinates.
_DISPLAY_COORDINATES_RE = re.compile(
    r'"displayCoordinates":\[([-+]?\d{1,3}(?:\.\d+)?),([-+]?\d{1,2}(?:\.\d+)?)\]'
)


def _tls_context() -> ssl.SSLContext:
    # Python's default context trims the cipher list, and Yandex's anti-bot
    # fingerprints the TLS handshake: a short link answers it 403 instead of
    # the redirect. OpenSSL's own DEFAULT list passes; certificate and
    # hostname verification stay on — set_ciphers does not touch them.
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT")
    return context


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
        connector = aiohttp.TCPConnector(ssl=_tls_context())
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.get(url, allow_redirects=True, max_redirects=10) as response:
                final = str(response.url)
                if not _is_org_page(final):
                    return final
                return _with_body_pin(final, await response.text())


def _is_org_page(url: str) -> bool:
    parts = urlsplit(url)
    return "yandex." in parts.netloc and "/maps/org/" in parts.path


def _with_body_pin(url: str, body: str) -> str:
    """Lift the page's own pin into the URL, so the one parser reads it.

    An organisation link says nothing in its address bar; downloading the page
    is the only way to its point. Appended as pt= — the same pin parameter a
    hand-shared Yandex link would carry.
    """
    match = _DISPLAY_COORDINATES_RE.search(body)
    if match is None:
        return url

    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}pt={match.group(1)},{match.group(2)}"


def _unwrap_consent(url: str) -> str:
    # In some regions Google parks the redirect behind a consent wall and
    # tucks the real destination into ?continue=.
    if "consent." not in urlsplit(url).netloc:
        return url

    for value in parse_qs(urlsplit(url).query).get("continue", []):
        return unquote(value)
    return url
