from typing import Protocol


class LinkResolver(Protocol):
    """Turns a short map link into the URL that actually holds coordinates.

    Short links (maps.app.goo.gl and kin) carry nothing in themselves; the
    coordinates live in the page they redirect to.
    """

    async def resolve(self, url: str) -> str | None:
        """The final URL after redirects, or None when the link went nowhere."""
