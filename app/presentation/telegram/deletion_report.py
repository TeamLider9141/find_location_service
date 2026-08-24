"""The deletion journal as a standalone HTML page.

Telegram text tops out at 4096 characters and reads poorly as a table, so the
full journal goes out as a document instead: one self-contained file, openable
in any browser, every deletion a row. Names are input and are escaped — the
same rule as everywhere else, only here a stray tag would corrupt a whole page
rather than one message.
"""

import html
from datetime import datetime, timedelta, timezone

from app.application.use_cases.admin import DeletionRow
from app.presentation.telegram.admin_formatters import DELETION_SOURCE_LABELS
from app.presentation.telegram.keyboards.categories import category_label

REPORT_FILENAME = "ochirishlar_jurnali.html"

_TASHKENT = timezone(timedelta(hours=5))

_PAGE = """<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<title>O'chirishlar jurnali</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f7f7f8; color: #1c1c1e; }}
  h1 {{ font-size: 1.3rem; }}
  p.meta {{ color: #6e6e73; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; }}
  th, td {{ border: 1px solid #d1d1d6; padding: 0.5rem 0.7rem;
           text-align: left; vertical-align: top; }}
  th {{ background: #ececf0; position: sticky; top: 0; }}
  tr:nth-child(even) td {{ background: #fafafa; }}
  a {{ color: #0a58ca; }}
</style>
</head>
<body>
<h1>🧾 O'chirishlar jurnali</h1>
<p class="meta">{count} ta yozuv · {generated} (Toshkent vaqti)</p>
<table>
<thead>
<tr>
  <th>#</th><th>Vaqt</th><th>Joy</th><th>Kategoriya</th>
  <th>Izoh</th><th>Qo'shgan</th><th>O'chirgan</th><th>Qayerdan</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""

_ROW = (
    "<tr><td>{index}</td><td>{stamp}</td>"
    '<td><a href="{link}">{name}</a></td>'
    "<td>{category}</td><td>{note}</td>"
    "<td>{author}</td><td>{deleter}</td><td>{source}</td></tr>"
)


def render_deletion_report(rows: list[DeletionRow]) -> str:
    body = "\n".join(_render_row(index, row) for index, row in enumerate(rows, start=1))
    return _PAGE.format(
        count=len(rows),
        generated=datetime.now(_TASHKENT).strftime("%Y-%m-%d %H:%M"),
        rows=body,
    )


def _render_row(index: int, row: DeletionRow) -> str:
    record = row.record
    link = (
        "https://www.google.com/maps/search/?api=1"
        f"&query={record.latitude},{record.longitude}"
    )
    stamp = (
        record.deleted_at.replace(tzinfo=timezone.utc)
        .astimezone(_TASHKENT)
        .strftime("%Y-%m-%d %H:%M")
    )
    return _ROW.format(
        index=index,
        stamp=stamp,
        link=html.escape(link, quote=True),
        name=html.escape(record.place_name),
        category=html.escape(category_label(record.category)),
        note=html.escape(record.note) or "—",
        author=html.escape(_named(row.added_by, record.added_by_user_id)),
        deleter=html.escape(_named(row.deleted_by, record.deleted_by_user_id)),
        source=html.escape(DELETION_SOURCE_LABELS.get(record.source, record.source)),
    )


def _named(user, user_id: int) -> str:
    if user is None:
        return str(user_id)
    name = user.full_name or str(user_id)
    return f"{name} (@{user.username})" if user.username else name
