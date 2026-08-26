import html

from app.application.use_cases.documents import DocumentCard, DocumentsPage
from app.domain.value_objects.attachment import AttachmentKind
from app.presentation.telegram.formatters import place_map_link

NO_DOCUMENTS_MESSAGE = (
    "Hali hujjat qo'shilmagan.\n\n"
    "➕ Hujjat qo'shish orqali manzilga hujjat biriktirish mumkin."
)
PLACE_GONE_LABEL = "Manzil o'chirilgan"
NOTE_PREFIX = "📝 Hujjat turlari:"
ATTACHMENT_LABELS = {
    AttachmentKind.PHOTO: "📎 Rasm biriktirilgan",
    AttachmentKind.FILE: "📎 Hujjat biriktirilgan",
}

# Seven full 200-word notes would blow through Telegram's 4096-character
# message; the list shows the head of each note, the numbered button under it
# opens the whole thing.
LIST_NOTE_PREVIEW_CHARS = 160

# Telegram cuts a media caption at 1024 characters.
CAPTION_LIMIT = 1024


def format_documents_page(page: DocumentsPage) -> str:
    """The shared list — sent with parse_mode="HTML", names escaped."""
    if not page.rows:
        return NO_DOCUMENTS_MESSAGE

    total_pages = max(1, -(-page.total // page.page_size))
    lines = [
        f"🗂 Manzildagi hujjatlar — {page.total} ta",
        f"Sahifa {page.page + 1}/{total_pages}",
        "",
    ]
    # Numbering continues across pages, same as the admin's user list: "1)" on
    # page two would read as a second first document.
    first_number = page.page * page.page_size + 1
    for index, card in enumerate(page.rows, start=first_number):
        lines.append(f"{index}) {_place_line(card)}")
        if card.document.has_attachment:
            lines.append(f"   {ATTACHMENT_LABELS[card.document.file_kind]}")
        lines.append(f"   📝 {html.escape(_shortened(card.document.note))}")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_document_caption(card: DocumentCard) -> str:
    """The full card — the caption under the attachment, or the message itself.

    Sent with parse_mode="HTML": the place name is the link, a naked URL under
    it would only repeat the line. Driver input — name and note — is escaped.
    A missing attachment says nothing; the absent file speaks for itself.
    """
    lines = [f"📍 {_place_line(card)}"]
    if card.document.has_attachment:
        lines.append(ATTACHMENT_LABELS[card.document.file_kind])
    lines.append("")
    lines.append(f"{NOTE_PREFIX} {html.escape(card.document.note)}")

    text = "\n".join(lines)
    if len(text) <= CAPTION_LIMIT:
        return text
    return text[: CAPTION_LIMIT - 1] + "…"


def _place_line(card: DocumentCard) -> str:
    if card.place is None:
        return PLACE_GONE_LABEL

    # The name is the link, as in the search results: tapping the line the
    # driver is already reading beats hunting a raw URL under it.
    name = html.escape(card.place.name)
    return f'<a href="{place_map_link(card.place)}">{name}</a>'


def _shortened(note: str) -> str:
    if len(note) <= LIST_NOTE_PREVIEW_CHARS:
        return note
    return note[: LIST_NOTE_PREVIEW_CHARS - 1] + "…"
