import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from app.domain.entities.place_document import PlaceDocument
from app.domain.value_objects.attachment import AttachmentKind

_COLUMNS = "id, place_id, added_by_user_id, note, file_id, file_kind, created_at"


class SQLiteDocumentRepository:
    """Documents pinned to places, kept across restarts.

    Only Telegram's file ids are stored, never the bytes: Telegram keeps the
    file and resends it on demand, so the database stays a database.
    """

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(self, document: PlaceDocument) -> PlaceDocument:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO place_documents (
                    place_id, added_by_user_id, note, file_id, file_kind
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    document.place_id,
                    document.added_by_user_id,
                    document.note,
                    document.file_id,
                    document.file_kind.value if document.file_kind else None,
                ),
            )
            connection.commit()
            document_id = int(cursor.lastrowid)

        stored = self.get(document_id)
        if stored is None:  # pragma: no cover - insert just succeeded
            raise RuntimeError("inserted document disappeared")
        return stored

    def get(self, document_id: int) -> PlaceDocument | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM place_documents WHERE id = ?",
                (document_id,),
            ).fetchone()

        return _map_row(row) if row is not None else None

    def list_page(self, offset: int, limit: int) -> tuple[int, list[PlaceDocument]]:
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM place_documents"
                ).fetchone()["total"]
            )
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} FROM place_documents
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (max(limit, 0), max(offset, 0)),
            ).fetchall()

        return total, [_map_row(row) for row in rows]

    def list_by_author(self, user_id: int) -> list[PlaceDocument]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} FROM place_documents
                WHERE added_by_user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()

        return [_map_row(row) for row in rows]

    def update(
        self,
        document_id: int,
        user_id: int,
        note: str | None = None,
        file_id: str | None = None,
        file_kind: AttachmentKind | None = None,
    ) -> PlaceDocument | None:
        assignments: list[str] = []
        parameters: list[object] = []
        if note is not None:
            assignments.append("note = ?")
            parameters.append(note)
        # Replaced as a pair: a file id without its kind could not be sent back.
        if file_id is not None and file_kind is not None:
            assignments.append("file_id = ?")
            parameters.append(file_id)
            assignments.append("file_kind = ?")
            parameters.append(file_kind.value)

        if not assignments:
            return self._get_owned(document_id, user_id)

        with closing(self._connect()) as connection:
            # Ownership sits in the WHERE: one statement both checks and
            # writes, so no window opens between the two.
            cursor = connection.execute(
                f"""
                UPDATE place_documents SET {", ".join(assignments)}
                WHERE id = ? AND added_by_user_id = ?
                """,
                (*parameters, document_id, user_id),
            )
            connection.commit()
            changed = cursor.rowcount

        return self.get(document_id) if changed else None

    def _get_owned(self, document_id: int, user_id: int) -> PlaceDocument | None:
        document = self.get(document_id)
        if document is None or document.added_by_user_id != user_id:
            return None
        return document

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS place_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    place_id INTEGER NOT NULL,
                    added_by_user_id INTEGER NOT NULL,
                    note TEXT NOT NULL,
                    file_id TEXT,
                    file_kind TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _map_row(row: Row) -> PlaceDocument:
    raw_kind = row["file_kind"]
    return PlaceDocument(
        id=int(row["id"]),
        place_id=int(row["place_id"]),
        added_by_user_id=int(row["added_by_user_id"]),
        note=str(row["note"]),
        file_id=str(row["file_id"]) if row["file_id"] else None,
        file_kind=AttachmentKind(raw_kind) if raw_kind else None,
        created_at=_parse_timestamp(str(row["created_at"])),
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min
