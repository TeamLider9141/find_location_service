"""The shared database, mailed to the supers when it has changed.

One copy a day is the whole backup story: the bot's own chat with its super
admins becomes an off-server history of the database, and a lost server costs
at most a day of contributions. Checked daily rather than sent daily — a week
of quiet does not deserve seven identical files.
"""

import asyncio
import hashlib
import logging
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 24 * 60 * 60
BACKUP_CAPTION = "🗄 Baza yangilandi — kunlik nusxa."


class DatabaseBackup:
    def __init__(
        self,
        bot: Bot,
        database_path: Path | str,
        super_admin_ids: tuple[int, ...],
        interval_seconds: float = CHECK_INTERVAL_SECONDS,
    ) -> None:
        self._bot = bot
        self._path = Path(database_path)
        self._recipients = super_admin_ids
        self._interval = interval_seconds
        self._last_sent_digest: str | None = None

    async def run(self) -> None:
        """Check forever, one interval apart. Cancelled with the bot itself.

        The first check comes a full interval after startup: a redeploy must
        not mail a copy nobody asked for, and the file at startup is the
        baseline the first comparison runs against anyway.
        """
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.check_and_send()
            except Exception as error:  # noqa: BLE001 - the loop outlives any one failure
                logger.warning("database backup check failed: %s", error)

    async def check_and_send(self) -> bool:
        """Send the database if it changed since the last send; say whether it went.

        The digest is remembered only after at least one copy lands: a send
        that reached nobody must not silence tomorrow's attempt.
        """
        data = self._snapshot()
        if data is None:
            return False

        digest = hashlib.sha256(data).hexdigest()
        if digest == self._last_sent_digest:
            return False

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"find_location_{stamp}.sqlite3"

        sent_any = False
        for admin_id in self._recipients:
            try:
                await self._bot.send_document(
                    admin_id,
                    BufferedInputFile(data, filename=filename),
                    caption=BACKUP_CAPTION,
                )
                sent_any = True
            except TelegramAPIError as error:
                # One blocked super must not cost the other their copy.
                logger.warning("database backup to %s failed: %s", admin_id, error)

        if sent_any:
            self._last_sent_digest = digest
        return sent_any

    def _snapshot(self) -> bytes | None:
        """A whole copy of the database, safe to take while the bot writes.

        SQLite's own backup API instead of reading the file raw: a raw read
        can catch the bytes between two pages of a write and mail a copy that
        does not open.
        """
        # connect() would create an empty database where none exists, and an
        # empty file mailed daily would read as "the data is gone".
        if not self._path.exists():
            logger.warning("database backup skipped: %s does not exist", self._path)
            return None

        try:
            with tempfile.TemporaryDirectory() as folder:
                copy_path = Path(folder) / self._path.name
                with closing(sqlite3.connect(self._path)) as source, closing(
                    sqlite3.connect(copy_path)
                ) as copy:
                    source.backup(copy)
                return copy_path.read_bytes()
        except (sqlite3.Error, OSError) as error:
            logger.warning("database backup snapshot failed: %s", error)
            return None
