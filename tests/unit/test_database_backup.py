import sqlite3
from contextlib import closing

from aiogram.exceptions import TelegramForbiddenError

from app.presentation.telegram.database_backup import (
    BACKUP_CAPTION,
    CHECK_INTERVAL_SECONDS,
    DatabaseBackup,
)


class FakeBot:
    def __init__(self, blocked: set[int] | None = None) -> None:
        self.documents: list[tuple[int, str, str | None]] = []
        self._blocked = blocked or set()

    async def send_document(self, chat_id, document, caption=None, **_: object) -> None:
        if chat_id in self._blocked:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        self.documents.append((chat_id, document.filename, caption))


def database(tmp_path):
    path = tmp_path / "bot.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE places (name TEXT)")
        connection.execute("INSERT INTO places VALUES ('Газпром')")
        connection.commit()
    return path


def grow(path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO places VALUES ('Кафе М5')")
        connection.commit()


async def test_the_first_check_mails_every_super(tmp_path) -> None:
    bot = FakeBot()
    backup = DatabaseBackup(bot, database(tmp_path), super_admin_ids=(1, 2))

    assert await backup.check_and_send() is True

    assert [chat_id for chat_id, _, _ in bot.documents] == [1, 2]
    assert all(name.endswith(".sqlite3") for _, name, _ in bot.documents)
    assert all(caption == BACKUP_CAPTION for _, _, caption in bot.documents)


async def test_an_unchanged_database_is_not_sent_again(tmp_path) -> None:
    # A week of quiet does not deserve seven identical files.
    bot = FakeBot()
    backup = DatabaseBackup(bot, database(tmp_path), super_admin_ids=(1,))
    await backup.check_and_send()

    assert await backup.check_and_send() is False
    assert len(bot.documents) == 1


async def test_a_changed_database_is_sent_again(tmp_path) -> None:
    bot = FakeBot()
    path = database(tmp_path)
    backup = DatabaseBackup(bot, path, super_admin_ids=(1,))
    await backup.check_and_send()

    grow(path)

    assert await backup.check_and_send() is True
    assert len(bot.documents) == 2


async def test_one_blocked_super_does_not_cost_the_other_their_copy(tmp_path) -> None:
    bot = FakeBot(blocked={1})
    backup = DatabaseBackup(bot, database(tmp_path), super_admin_ids=(1, 2))

    assert await backup.check_and_send() is True
    assert [chat_id for chat_id, _, _ in bot.documents] == [2]


async def test_a_send_that_reached_nobody_retries_next_time(tmp_path) -> None:
    # The digest is remembered only after a copy lands, so tomorrow tries again.
    bot = FakeBot(blocked={1})
    backup = DatabaseBackup(bot, database(tmp_path), super_admin_ids=(1,))

    assert await backup.check_and_send() is False

    unblocked = FakeBot()
    backup._bot = unblocked

    assert await backup.check_and_send() is True


async def test_a_missing_file_is_a_quiet_no(tmp_path) -> None:
    backup = DatabaseBackup(FakeBot(), tmp_path / "missing.sqlite3", super_admin_ids=(1,))

    assert await backup.check_and_send() is False


def test_the_default_interval_is_a_day() -> None:
    assert CHECK_INTERVAL_SECONDS == 24 * 60 * 60


async def test_the_mailed_copy_is_a_database_that_opens(tmp_path) -> None:
    # Snapshotted through sqlite's backup API, not read raw: a raw read can
    # catch the file mid-write and mail a copy that does not open.
    class Capture(FakeBot):
        async def send_document(self, chat_id, document, caption=None, **_):
            self.payload = document.data
            await super().send_document(chat_id, document, caption)

    bot = Capture()
    await DatabaseBackup(bot, database(tmp_path), super_admin_ids=(1,)).check_and_send()

    assert bot.payload.startswith(b"SQLite format 3")
