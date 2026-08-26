import html
import sqlite3
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.access import HasAddAccessUseCase
from app.application.use_cases.documents import (
    AddDocumentUseCase,
    CountDocumentsByPlaceUseCase,
    DocumentCard,
    GetDocumentUseCase,
    ListDocumentsPageUseCase,
    ListMyDocumentsUseCase,
    NOTE_WORD_LIMIT,
    UpdateDocumentUseCase,
    note_within_limit,
)
from app.application.use_cases.places import FindPlacesUseCase, GetPlaceUseCase
from app.domain.entities.place_document import PlaceDocument
from app.domain.value_objects.attachment import AttachmentKind
from app.presentation.telegram.access import is_admin
from app.presentation.telegram.document_formatters import (
    NO_DOCUMENTS_MESSAGE,
    format_document_caption,
    format_documents_page,
)
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import place_map_link
from app.presentation.telegram.prompts import with_cancel_hint
from app.presentation.telegram.keyboards.documents import (
    build_document_preview_keyboard,
    build_documents_page_keyboard,
    build_my_data_keyboard,
    build_my_document_actions_keyboard,
    build_place_pick_keyboard,
)
from app.presentation.telegram.keyboards.menu import (
    ADD_DOCUMENT_BUTTON,
    DOCUMENTS_BUTTON,
    MY_DATA_BUTTON,
)
from app.presentation.telegram.states import AddDocument, EditDocument

router = Router(name="documents")

CLOSED_MESSAGE = (
    "🔒 Bu bo'lim faqat joy qo'shish ruxsati borlar va adminlar uchun.\n"
    "Ruxsat olish uchun ➕ Joy qo'shish tugmasini bosing — so'rov adminga boradi."
)
MY_DATA_MESSAGE = "📁 Mening ma'lumotlarim\n\nQaysi bo'limni ochamiz?"
EMPTY_MY_DOCUMENTS_MESSAGE = (
    "Siz hali hujjat qo'shmagansiz.\n\n"
    "➕ Hujjat qo'shish orqali manzilga hujjat biriktiring."
)
NO_PLACES_MESSAGE = (
    "Bazada hali manzil yo'q — hujjatni biriktirishga joy topilmadi.\n"
    "Avval ➕ Joy qo'shish orqali manzil qo'shing."
)
ATTACH_PLACE_MESSAGE = with_cancel_hint(
    "Manzil ulash — hujjat qaysi manzilga tegishli? Ro'yxatdan tanlang:"
)
# The name carries the map link so the driver can check they picked the right
# place before writing anything; the place's own note rides under it.
PLACE_CHOSEN_TEMPLATE = with_cancel_hint(
    '✅ Manzil tanlandi: <a href="{link}">{name}</a>\n'
    "{note_line}\n"
    "Endi unga hujjat biriktirish uchun izoh yozing — hujjat turlari, "
    "nimalar kerakligi ({limit} so'zgacha).\n"
    "Rasm (png/jpg) yoki hujjat (pdf, doc, docx) ham tashlashingiz mumkin."
)
FILE_RECEIVED_MESSAGE = with_cancel_hint("📎 Hujjat tashlandi. Endi tagiga izoh yozing.")
FILE_REPLACED_MESSAGE = "📎 Hujjat almashtirildi."
UNSUPPORTED_FILE_MESSAGE = with_cancel_hint(
    "Bu turdagi fayl qabul qilinmaydi. "
    "Rasm (png/jpg) yoki pdf, doc, docx hujjat yuboring."
)
NOTE_TOO_LONG_TEMPLATE = with_cancel_hint(
    "Izoh {limit} so'zdan oshmasin. Qisqartirib yozing."
)
BLANK_NOTE_MESSAGE = with_cancel_hint("Izoh bo'sh bo'lmasligi kerak. Hujjat haqida yozing.")
PREVIEW_MESSAGE = "Namunaviy hujjat ko'rinishi — saqlansa shunday ko'rinadi:"
ASK_NEW_FILE_MESSAGE = with_cancel_hint("Yangi rasm yoki hujjat tashlang.")
ASK_NEW_NOTE_MESSAGE = with_cancel_hint("Yangi izoh yozing.")
SAVED_MESSAGE = "✅ Hujjat saqlandi."
UPDATED_MESSAGE = "✅ Yangilandi."
NOT_YOURS_MESSAGE = "Bu hujjatni faqat uni qo'shgan foydalanuvchi o'zgartira oladi."
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qaytadan urinib ko'ring."
PLACE_GONE_MESSAGE = "Bu manzil o'chirilgan. Boshqa manzil tanlang."
DOCUMENT_GONE_MESSAGE = "Bu hujjat topilmadi."
SAVE_FAILED_MESSAGE = "Saqlab bo'lmadi. Qaytadan urinib ko'ring."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."

_PLACE_KEY = "doc_place_id"
_NOTE_KEY = "doc_note"
_FILE_ID_KEY = "doc_file_id"
_FILE_KIND_KEY = "doc_file_kind"
_EDIT_DOCUMENT_KEY = "edit_document_id"

# What a driver may pin: pictures and the office formats documents come in.
_ALLOWED_EXTENSIONS = (".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg")


# --- The shared list -------------------------------------------------------


@router.message(F.text == DOCUMENTS_BUTTON)
async def handle_documents_list(
    message: Message, list_documents_page: ListDocumentsPageUseCase
) -> None:
    await _send_documents_page(message, list_documents_page, page=0)


@router.callback_query(F.data.startswith("docs:page:"))
async def handle_documents_page(
    callback_query: CallbackQuery, list_documents_page: ListDocumentsPageUseCase
) -> None:
    page = _parse_id(callback_query.data, "docs:page:")
    message = answerable_message(callback_query)
    if page is None or message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await _send_documents_page(message, list_documents_page, page=page)
    await callback_query.answer()


async def _send_documents_page(
    message: Message, list_documents_page: ListDocumentsPageUseCase, page: int
) -> None:
    try:
        documents_page = list_documents_page.execute(page=page)
    except sqlite3.Error as error:
        report_service_error(error, "documents page")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    if not documents_page.rows:
        await message.answer(NO_DOCUMENTS_MESSAGE)
        return

    await message.answer(
        format_documents_page(documents_page),
        reply_markup=build_documents_page_keyboard(documents_page),
        parse_mode="HTML",
        # Every entry carries a map link; seven previews would bury the list.
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("docs:open:"))
async def handle_document_open(
    callback_query: CallbackQuery, get_document: GetDocumentUseCase
) -> None:
    document_id = _parse_id(callback_query.data, "docs:open:")
    message = answerable_message(callback_query)
    if document_id is None or message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        card = get_document.execute(document_id)
    except sqlite3.Error as error:
        report_service_error(error, "open document")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if card is None:
        await callback_query.answer(DOCUMENT_GONE_MESSAGE)
        return

    await _send_document_card(message, card)
    await callback_query.answer()


# --- My data ---------------------------------------------------------------


@router.message(F.text == MY_DATA_BUTTON)
async def handle_my_data(
    message: Message,
    admin_ids: tuple[int, ...],
    has_add_access: HasAddAccessUseCase,
) -> None:
    # The button is drawn for everyone; the section behind it is not. Locked
    # rather than hidden, so a driver learns the section exists and how to ask.
    if not _may_contribute(message, admin_ids, has_add_access):
        await message.answer(CLOSED_MESSAGE)
        return

    await message.answer(MY_DATA_MESSAGE, reply_markup=build_my_data_keyboard())


@router.callback_query(F.data == "my_data:documents")
async def handle_my_documents(
    callback_query: CallbackQuery, list_my_documents: ListMyDocumentsUseCase
) -> None:
    user_id = user_id_of(callback_query)
    message = answerable_message(callback_query)
    if user_id is None or message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        cards = list_my_documents.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "list my documents")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if not cards:
        await message.answer(EMPTY_MY_DOCUMENTS_MESSAGE)
        await callback_query.answer()
        return

    # One message per document, as with places: the edit buttons under a card
    # target a single document, so two cannot share one card.
    for card in cards:
        await _send_document_card(
            message,
            card,
            reply_markup=build_my_document_actions_keyboard(card.document.id),
        )
    await callback_query.answer()


# --- Adding a document -----------------------------------------------------


@router.message(F.text == ADD_DOCUMENT_BUTTON)
async def handle_add_document_start(
    message: Message,
    state: FSMContext,
    admin_ids: tuple[int, ...],
    has_add_access: HasAddAccessUseCase,
    find_places: FindPlacesUseCase,
    count_documents_by_place: CountDocumentsByPlaceUseCase,
) -> None:
    if not _may_contribute(message, admin_ids, has_add_access):
        await message.answer(CLOSED_MESSAGE)
        return

    picking = await _places_for_picking(message, find_places, count_documents_by_place)
    if picking is None:
        return
    places, documented = picking
    if not places:
        await message.answer(NO_PLACES_MESSAGE)
        return

    # Clear first: an abandoned flow leaves its place id in storage, and
    # carrying it into a fresh attempt would pin the new document to it.
    await state.set_data({})
    await state.set_state(AddDocument.place)
    await message.answer(
        ATTACH_PLACE_MESSAGE,
        reply_markup=build_place_pick_keyboard(places, page=0, documented=documented),
    )


@router.callback_query(AddDocument.place, F.data.startswith("add_doc:pick_page:"))
async def handle_pick_page(
    callback_query: CallbackQuery,
    find_places: FindPlacesUseCase,
    count_documents_by_place: CountDocumentsByPlaceUseCase,
) -> None:
    page = _parse_id(callback_query.data, "add_doc:pick_page:")
    message = answerable_message(callback_query)
    if page is None or message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    picking = await _places_for_picking(message, find_places, count_documents_by_place)
    if not picking or not picking[0]:
        await callback_query.answer()
        return

    places, documented = picking
    # Redraw in place: paging through fifty places must not leave fifty
    # keyboards behind.
    try:
        await message.edit_reply_markup(
            reply_markup=build_place_pick_keyboard(
                places, page=page, documented=documented
            )
        )
    except TelegramAPIError as error:
        report_service_error(error, "place pick page")
    await callback_query.answer()


@router.callback_query(AddDocument.place, F.data.startswith("add_doc:place:"))
async def handle_place_chosen(
    callback_query: CallbackQuery,
    state: FSMContext,
    get_place: GetPlaceUseCase,
) -> None:
    place_id = _parse_id(callback_query.data, "add_doc:place:")
    message = answerable_message(callback_query)
    if place_id is None or message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        place = get_place.execute(place_id)
    except sqlite3.Error as error:
        report_service_error(error, "document place")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if place is None:
        await callback_query.answer(PLACE_GONE_MESSAGE)
        return

    await state.update_data(**{_PLACE_KEY: place.id})
    await state.set_state(AddDocument.content)
    note_line = f"📝 {html.escape(place.note)}\n" if place.note else ""
    await message.answer(
        PLACE_CHOSEN_TEMPLATE.format(
            link=place_map_link(place),
            name=html.escape(place.name),
            note_line=note_line,
            limit=NOTE_WORD_LIMIT,
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback_query.answer()


@router.message(AddDocument.content, F.photo)
async def handle_content_photo(
    message: Message, state: FSMContext, get_place: GetPlaceUseCase
) -> None:
    # The last size is the largest; Telegram orders them small to big.
    await _take_file(
        message, state, get_place, message.photo[-1].file_id, AttachmentKind.PHOTO
    )


@router.message(AddDocument.content, F.document)
async def handle_content_document(
    message: Message, state: FSMContext, get_place: GetPlaceUseCase
) -> None:
    if not _acceptable_file(message.document):
        await message.answer(UNSUPPORTED_FILE_MESSAGE)
        return

    await _take_file(
        message, state, get_place, message.document.file_id, AttachmentKind.FILE
    )


async def _take_file(
    message: Message,
    state: FSMContext,
    get_place: GetPlaceUseCase,
    file_id: str,
    kind: AttachmentKind,
) -> None:
    """Accept the attachment, then ask for — or return to — the note."""
    await state.update_data(**{_FILE_ID_KEY: file_id, _FILE_KIND_KEY: kind.value})
    data = await state.get_data()

    # Two roads lead here: the first upload, and the preview's "re-upload"
    # button. The second already has its note — the driver was done writing.
    if data.get(_NOTE_KEY):
        await _show_preview(message, state, get_place)
    else:
        await message.answer(FILE_RECEIVED_MESSAGE)


@router.message(AddDocument.content, F.text)
async def handle_content_note(
    message: Message, state: FSMContext, get_place: GetPlaceUseCase
) -> None:
    note = (message.text or "").strip()
    if not note:
        await message.answer(BLANK_NOTE_MESSAGE)
        return
    if not note_within_limit(note):
        await message.answer(NOTE_TOO_LONG_TEMPLATE.format(limit=NOTE_WORD_LIMIT))
        return

    await state.update_data(**{_NOTE_KEY: note})
    await _show_preview(message, state, get_place)


async def _show_preview(
    message: Message, state: FSMContext, get_place: GetPlaceUseCase
) -> None:
    """Show the document exactly as everyone will see it, before it is written."""
    data = await state.get_data()
    try:
        place = get_place.execute(int(data[_PLACE_KEY]))
        card = DocumentCard(document=_draft_document(data), place=place)
    except (KeyError, ValueError) as error:
        # A flow that lost a step leaves the state short of a key; better to
        # start over than to preview a document that cannot be saved.
        report_service_error(error, "document preview")
        await state.clear()
        await message.answer(SAVE_FAILED_MESSAGE)
        return
    except sqlite3.Error as error:
        report_service_error(error, "document preview")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await state.set_state(AddDocument.preview)
    await _send_document_card(
        message,
        card,
        reply_markup=build_document_preview_keyboard(),
        header=PREVIEW_MESSAGE,
    )


@router.callback_query(AddDocument.preview, F.data == "add_doc:refile")
async def handle_preview_refile(
    callback_query: CallbackQuery, state: FSMContext
) -> None:
    await _back_to_content(callback_query, state, ASK_NEW_FILE_MESSAGE)


@router.callback_query(AddDocument.preview, F.data == "add_doc:renote")
async def handle_preview_renote(
    callback_query: CallbackQuery, state: FSMContext
) -> None:
    await _back_to_content(callback_query, state, ASK_NEW_NOTE_MESSAGE)


async def _back_to_content(
    callback_query: CallbackQuery, state: FSMContext, ask: str
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await state.clear()
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await state.set_state(AddDocument.content)
    await message.answer(ask)
    await callback_query.answer()


@router.callback_query(AddDocument.preview, F.data == "add_doc:save")
async def handle_preview_save(
    callback_query: CallbackQuery,
    state: FSMContext,
    add_document: AddDocumentUseCase,
) -> None:
    message = answerable_message(callback_query)
    user_id = user_id_of(callback_query)
    if message is None or user_id is None:
        await state.clear()
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    data = await state.get_data()
    try:
        draft = _draft_document(data)
        card = add_document.execute(
            user_id=user_id,
            place_id=draft.place_id,
            note=draft.note,
            file_id=draft.file_id,
            file_kind=draft.file_kind,
        )
    except (KeyError, ValueError) as error:
        report_service_error(error, "save document")
        await state.clear()
        await message.answer(SAVE_FAILED_MESSAGE)
        await callback_query.answer()
        return
    except sqlite3.Error as error:
        report_service_error(error, "save document")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await state.clear()
    if card is None:
        # The place aged out between picking it and saving.
        await message.answer(PLACE_GONE_MESSAGE)
        await callback_query.answer()
        return

    await _send_document_card(message, card, header=SAVED_MESSAGE)
    await callback_query.answer()


# --- Editing my documents --------------------------------------------------


@router.callback_query(F.data.startswith("my_doc:renote:"))
async def handle_edit_note_prompt(
    callback_query: CallbackQuery, state: FSMContext
) -> None:
    await _prompt_edit(
        callback_query, state, "my_doc:renote:", EditDocument.note, ASK_NEW_NOTE_MESSAGE
    )


@router.callback_query(F.data.startswith("my_doc:refile:"))
async def handle_edit_file_prompt(
    callback_query: CallbackQuery, state: FSMContext
) -> None:
    await _prompt_edit(
        callback_query, state, "my_doc:refile:", EditDocument.file, ASK_NEW_FILE_MESSAGE
    )


async def _prompt_edit(
    callback_query: CallbackQuery,
    state: FSMContext,
    prefix: str,
    next_state,
    ask: str,
) -> None:
    # Ownership is not checked here: the write itself refuses a stranger, and
    # one source of truth beats a prompt-time check a forged callback could
    # outrun anyway.
    document_id = _parse_id(callback_query.data, prefix)
    if document_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await state.set_state(next_state)
    await state.update_data(**{_EDIT_DOCUMENT_KEY: document_id})
    await message.answer(ask)
    await callback_query.answer()


@router.message(EditDocument.note, F.text)
async def handle_edit_note(
    message: Message, state: FSMContext, update_document: UpdateDocumentUseCase
) -> None:
    note = (message.text or "").strip()
    if not note:
        await message.answer(BLANK_NOTE_MESSAGE)
        return
    if not note_within_limit(note):
        await message.answer(NOTE_TOO_LONG_TEMPLATE.format(limit=NOTE_WORD_LIMIT))
        return

    await _apply_edit(message, state, update_document, note=note)


@router.message(EditDocument.file, F.photo)
async def handle_edit_photo(
    message: Message, state: FSMContext, update_document: UpdateDocumentUseCase
) -> None:
    await _apply_edit(
        message,
        state,
        update_document,
        file_id=message.photo[-1].file_id,
        file_kind=AttachmentKind.PHOTO,
    )


@router.message(EditDocument.file, F.document)
async def handle_edit_file(
    message: Message, state: FSMContext, update_document: UpdateDocumentUseCase
) -> None:
    if not _acceptable_file(message.document):
        await message.answer(UNSUPPORTED_FILE_MESSAGE)
        return

    await _apply_edit(
        message,
        state,
        update_document,
        file_id=message.document.file_id,
        file_kind=AttachmentKind.FILE,
    )


async def _apply_edit(
    message: Message,
    state: FSMContext,
    update_document: UpdateDocumentUseCase,
    **changes,
) -> None:
    data = await state.get_data()
    raw_document_id = data.get(_EDIT_DOCUMENT_KEY)
    user_id = user_id_of(message)
    await state.clear()

    if raw_document_id is None or user_id is None:
        await message.answer(INVALID_SELECTION_MESSAGE)
        return

    try:
        card = update_document.execute(
            document_id=int(raw_document_id), user_id=user_id, **changes
        )
    except sqlite3.Error as error:
        report_service_error(error, "edit document")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    # The refusal comes from the update itself returning None rather than a
    # separate ownership read: one source of truth for who may edit.
    if card is None:
        await message.answer(NOT_YOURS_MESSAGE)
        return

    await _send_document_card(
        message,
        card,
        reply_markup=build_my_document_actions_keyboard(card.document.id),
        header=UPDATED_MESSAGE,
    )


# --- Shared helpers --------------------------------------------------------


async def _send_document_card(
    message: Message,
    card: DocumentCard,
    reply_markup=None,
    header: str | None = None,
) -> None:
    """One document as one message: the attachment itself with the note under
    it, or plain text when nothing is pinned."""
    caption = format_document_caption(card)
    if header:
        caption = f"{header}\n\n{caption}"

    # HTML everywhere: the place name in the caption is the map link.
    document = card.document
    if document.file_kind is AttachmentKind.PHOTO and document.file_id:
        await message.answer_photo(
            document.file_id,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    elif document.file_kind is AttachmentKind.FILE and document.file_id:
        await message.answer_document(
            document.file_id,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


async def _places_for_picking(
    message: Message,
    find_places: FindPlacesUseCase,
    count_documents_by_place: CountDocumentsByPlaceUseCase,
) -> tuple[list, frozenset[int]] | None:
    """Every place ranked for the picker, or None after reporting the outage.

    Places already carrying documents lead the list — they are where papers
    are asked for, so they are where the next document most likely belongs —
    and the returned set marks them so the keyboard can say why.
    """
    try:
        places = find_places.execute(limit=-1)
        documented = frozenset(
            place_id
            for place_id, total in count_documents_by_place.execute().items()
            if total > 0
        )
    except sqlite3.Error as error:
        report_service_error(error, "places for document")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return None

    # A stable sort: the documented rise, everyone else keeps their order.
    return sorted(places, key=lambda place: place.id not in documented), documented


def _draft_document(data: dict) -> PlaceDocument:
    """The document the flow's state describes, before it has an id."""
    raw_kind = data.get(_FILE_KIND_KEY)
    return PlaceDocument(
        id=0,
        place_id=int(data[_PLACE_KEY]),
        added_by_user_id=0,
        note=str(data[_NOTE_KEY]),
        file_id=data.get(_FILE_ID_KEY),
        file_kind=AttachmentKind(raw_kind) if raw_kind else None,
        created_at=datetime.min,
    )


def _may_contribute(
    update: object, admin_ids: tuple[int, ...], has_add_access: HasAddAccessUseCase
) -> bool:
    """Documents ride on the same right as places: the admin's nod, or being one."""
    if is_admin(update, admin_ids):
        return True

    user_id = user_id_of(update)
    if user_id is None:
        return False

    try:
        return has_add_access.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "document access check")
        return False


def _acceptable_file(document) -> bool:
    """Pictures in any format Telegram calls an image, plus pdf/doc/docx."""
    mime = (getattr(document, "mime_type", None) or "").lower()
    if mime.startswith("image/"):
        return True

    name = (getattr(document, "file_name", None) or "").lower()
    return name.endswith(_ALLOWED_EXTENSIONS)


def _parse_id(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    return int(raw) if raw.isdigit() else None
