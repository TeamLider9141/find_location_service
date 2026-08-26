import sqlite3

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.application.use_cases.access import DecideAddAccessUseCase, HasAddAccessUseCase
from app.application.use_cases.documents import (
    AddDocumentUseCase,
    CountDocumentsByPlaceUseCase,
    GetDocumentUseCase,
    ListDocumentsPageUseCase,
    ListMyDocumentsUseCase,
    UpdateDocumentUseCase,
)
from app.application.use_cases.places import AddPlaceUseCase, FindPlacesUseCase, GetPlaceUseCase
from app.domain.value_objects.attachment import AttachmentKind
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository
from app.infrastructure.repositories.in_memory_documents import InMemoryDocumentRepository
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.handlers.documents import (
    CLOSED_MESSAGE,
    FILE_RECEIVED_MESSAGE,
    NOT_YOURS_MESSAGE,
    UNSUPPORTED_FILE_MESSAGE,
    handle_add_document_start,
    handle_content_document,
    handle_content_note,
    handle_content_photo,
    handle_document_open,
    handle_documents_list,
    handle_edit_file_prompt,
    handle_edit_note,
    handle_edit_note_prompt,
    handle_edit_photo,
    handle_my_data,
    handle_my_documents,
    handle_place_chosen,
    handle_preview_refile,
    handle_preview_save,
)
from app.presentation.telegram.states import AddDocument, EditDocument


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.full_name = "Ali"
        self.username = None


class FakePhotoSize:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class FakeAttachment:
    def __init__(self, file_id: str, file_name: str | None, mime_type: str | None) -> None:
        self.file_id = file_id
        self.file_name = file_name
        self.mime_type = mime_type


class FakeMessage:
    def __init__(
        self,
        user_id: int = 42,
        text: str = "",
        photo: list[FakePhotoSize] | None = None,
        document: FakeAttachment | None = None,
    ) -> None:
        self.from_user = FakeUser(user_id)
        self.text = text
        self.photo = photo
        self.document = document
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"kind": "text", "text": text, **kwargs})

    async def answer_photo(self, photo: str, caption: str = "", **kwargs: object) -> None:
        self.answers.append({"kind": "photo", "file": photo, "text": caption, **kwargs})

    async def answer_document(self, document: str, caption: str = "", **kwargs: object) -> None:
        self.answers.append({"kind": "document", "file": document, "text": caption, **kwargs})

    async def edit_reply_markup(self, reply_markup=None) -> None:
        self.answers.append({"kind": "markup", "reply_markup": reply_markup})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id)
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


def make_state(user_id: int = 42) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=0, chat_id=user_id, user_id=user_id),
    )


class World:
    """Every dependency the document handlers ask for, over in-memory storage."""

    def __init__(self, approved: tuple[int, ...] = (42,)) -> None:
        self.places = InMemoryPlaceRepository()
        self.documents = InMemoryDocumentRepository()
        access = InMemoryAddAccessRepository()
        for user_id in approved:
            DecideAddAccessUseCase(access).execute(user_id, allow=True)
        self.has_add_access = HasAddAccessUseCase(access)
        self.find_places = FindPlacesUseCase(self.places)
        self.get_place = GetPlaceUseCase(self.places)
        self.add_document = AddDocumentUseCase(self.documents, self.places)
        self.list_documents_page = ListDocumentsPageUseCase(self.documents, self.places)
        self.list_my_documents = ListMyDocumentsUseCase(self.documents, self.places)
        self.get_document = GetDocumentUseCase(self.documents, self.places)
        self.update_document = UpdateDocumentUseCase(self.documents, self.places)
        self.count_documents_by_place = CountDocumentsByPlaceUseCase(self.documents)

    def place(self, name: str = "Газпром"):
        return AddPlaceUseCase(self.places).execute(
            user_id=42,
            name=name,
            categories=(PlaceCategory.FUEL,),
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
        )

    def document(self, user_id: int = 42, note: str = "CMR kerak", **kwargs):
        place = self.place()
        return self.add_document.execute(
            user_id=user_id, place_id=place.id, note=note, **kwargs
        )


def texts(message: FakeMessage) -> str:
    return "\n".join(str(answer["text"]) for answer in message.answers)


# --- Gates -----------------------------------------------------------------


async def test_my_data_is_closed_to_a_plain_driver() -> None:
    world = World(approved=())
    message = FakeMessage(user_id=7)

    await handle_my_data(message, admin_ids=(), has_add_access=world.has_add_access)

    assert CLOSED_MESSAGE in texts(message)


async def test_my_data_opens_for_an_approved_driver() -> None:
    world = World(approved=(42,))
    message = FakeMessage(user_id=42)

    await handle_my_data(message, admin_ids=(), has_add_access=world.has_add_access)

    keyboard = message.answers[0]["reply_markup"]
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == ["my_data:places", "my_data:documents"]


async def test_my_data_opens_for_an_admin_without_approval() -> None:
    world = World(approved=())
    message = FakeMessage(user_id=99)

    await handle_my_data(message, admin_ids=(99,), has_add_access=world.has_add_access)

    assert message.answers[0].get("reply_markup") is not None


async def test_adding_a_document_is_closed_to_a_plain_driver() -> None:
    world = World(approved=())
    message = FakeMessage(user_id=7)

    await handle_add_document_start(
        message,
        make_state(),
        admin_ids=(),
        has_add_access=world.has_add_access,
        find_places=world.find_places,
        count_documents_by_place=world.count_documents_by_place,
    )

    assert CLOSED_MESSAGE in texts(message)


# --- The shared list -------------------------------------------------------


async def test_an_empty_document_list_says_so() -> None:
    world = World()
    message = FakeMessage()

    await handle_documents_list(message, world.list_documents_page)

    assert "qo'shilmagan" in texts(message)


async def test_the_list_shows_numbered_documents_with_buttons() -> None:
    world = World()
    saved = world.document(note="Yuk xati va CMR")
    message = FakeMessage()

    await handle_documents_list(message, world.list_documents_page)

    text = texts(message)
    assert "1)" in text
    assert "Yuk xati va CMR" in text
    keyboard = message.answers[0]["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == f"docs:open:{saved.document.id}"


async def test_opening_a_document_sends_its_attachment() -> None:
    world = World()
    saved = world.document(file_id="PHOTO1", file_kind=AttachmentKind.PHOTO)
    callback = FakeCallbackQuery(f"docs:open:{saved.document.id}")

    await handle_document_open(callback, world.get_document)

    sent = callback.message.answers[0]
    assert sent["kind"] == "photo"
    assert sent["file"] == "PHOTO1"
    assert "CMR kerak" in str(sent["text"])


# --- Adding ----------------------------------------------------------------


async def test_the_flow_walks_place_file_note_preview_save() -> None:
    world = World()
    place = world.place()
    state = make_state()

    start = FakeMessage()
    await handle_add_document_start(
        start,
        state,
        admin_ids=(),
        has_add_access=world.has_add_access,
        find_places=world.find_places,
        count_documents_by_place=world.count_documents_by_place,
    )
    assert await state.get_state() == AddDocument.place
    pick_keyboard = start.answers[0]["reply_markup"]
    assert pick_keyboard.inline_keyboard[0][0].callback_data == f"add_doc:place:{place.id}"

    chosen = FakeCallbackQuery(f"add_doc:place:{place.id}")
    await handle_place_chosen(chosen, state, world.get_place)
    assert await state.get_state() == AddDocument.content
    confirmation = texts(chosen.message)
    assert "Manzil tanlandi" in confirmation
    # The name carries the map link, so the pick can be checked on the spot.
    assert '<a href="' in confirmation

    upload = FakeMessage(photo=[FakePhotoSize("SMALL"), FakePhotoSize("BIG")])
    await handle_content_photo(upload, state, world.get_place)
    assert FILE_RECEIVED_MESSAGE in texts(upload)

    note = FakeMessage(text="CMR, invoys va yuk xati")
    await handle_content_note(note, state, world.get_place)
    assert await state.get_state() == AddDocument.preview
    preview = note.answers[0]
    # The preview is the attachment itself — the largest photo size.
    assert preview["kind"] == "photo"
    assert preview["file"] == "BIG"

    save = FakeCallbackQuery("add_doc:save")
    await handle_preview_save(save, state, world.add_document)
    assert await state.get_state() is None
    assert "saqlandi" in texts(save.message).lower()
    assert world.documents.list_page(0, 10)[0] == 1


async def test_a_note_alone_is_enough() -> None:
    world = World()
    place = world.place()
    state = make_state()
    await state.set_state(AddDocument.content)
    await state.update_data(doc_place_id=place.id)

    note = FakeMessage(text="Faqat izoh")
    await handle_content_note(note, state, world.get_place)

    assert await state.get_state() == AddDocument.preview
    # No attachment: the preview is a plain message, and it does not
    # announce the absence — the missing file speaks for itself.
    assert note.answers[0]["kind"] == "text"
    assert "Biriktirilmagan" not in str(note.answers[0]["text"])


async def test_an_alien_file_type_is_refused() -> None:
    world = World()
    state = make_state()
    await state.set_state(AddDocument.content)

    upload = FakeMessage(
        document=FakeAttachment("EXE1", "virus.exe", "application/x-msdownload")
    )
    await handle_content_document(upload, state, world.get_place)

    assert UNSUPPORTED_FILE_MESSAGE in texts(upload)
    assert await state.get_state() == AddDocument.content


async def test_a_pdf_is_accepted() -> None:
    world = World()
    place = world.place()
    state = make_state()
    await state.set_state(AddDocument.content)
    await state.update_data(doc_place_id=place.id)

    upload = FakeMessage(document=FakeAttachment("PDF1", "hujjat.pdf", "application/pdf"))
    await handle_content_document(upload, state, world.get_place)

    assert FILE_RECEIVED_MESSAGE in texts(upload)


async def test_a_note_over_the_word_limit_is_sent_back() -> None:
    world = World()
    state = make_state()
    await state.set_state(AddDocument.content)

    note = FakeMessage(text="so'z " * 201)
    await handle_content_note(note, state, world.get_place)

    assert "200 so'zdan oshmasin" in texts(note)
    assert await state.get_state() == AddDocument.content


async def test_reuploading_from_the_preview_returns_to_the_preview() -> None:
    world = World()
    place = world.place()
    state = make_state()
    await state.set_state(AddDocument.preview)
    await state.update_data(doc_place_id=place.id, doc_note="izoh")

    refile = FakeCallbackQuery("add_doc:refile")
    await handle_preview_refile(refile, state)
    assert await state.get_state() == AddDocument.content

    upload = FakeMessage(photo=[FakePhotoSize("NEW")])
    await handle_content_photo(upload, state, world.get_place)

    # The note already exists, so the new file goes straight back to preview.
    assert await state.get_state() == AddDocument.preview
    assert upload.answers[0]["file"] == "NEW"


# --- My documents ----------------------------------------------------------


async def test_my_documents_lists_only_mine_with_edit_buttons() -> None:
    world = World()
    mine = world.document(user_id=42, note="meniki")
    world.add_document.execute(user_id=7, place_id=mine.place.id, note="boshqaniki")
    callback = FakeCallbackQuery("my_data:documents", user_id=42)

    await handle_my_documents(callback, world.list_my_documents)

    text = texts(callback.message)
    assert "meniki" in text
    assert "boshqaniki" not in text
    keyboard = callback.message.answers[0]["reply_markup"]
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == [
        f"my_doc:refile:{mine.document.id}",
        f"my_doc:renote:{mine.document.id}",
        f"my_doc:delete:{mine.document.id}",
    ]


async def test_editing_the_note_rewrites_it() -> None:
    world = World()
    saved = world.document(user_id=42)
    state = make_state()

    prompt = FakeCallbackQuery(f"my_doc:renote:{saved.document.id}", user_id=42)
    await handle_edit_note_prompt(prompt, state)
    assert await state.get_state() == EditDocument.note

    note = FakeMessage(user_id=42, text="yangi izoh")
    await handle_edit_note(note, state, world.update_document)

    assert world.documents.get(saved.document.id).note == "yangi izoh"
    assert "Yangilandi" in texts(note)


async def test_replacing_the_file_keeps_the_note() -> None:
    world = World()
    saved = world.document(user_id=42, file_id="OLD", file_kind=AttachmentKind.FILE)
    state = make_state()

    await handle_edit_file_prompt(
        FakeCallbackQuery(f"my_doc:refile:{saved.document.id}", user_id=42), state
    )
    upload = FakeMessage(user_id=42, photo=[FakePhotoSize("NEWPIC")])
    await handle_edit_photo(upload, state, world.update_document)

    stored = world.documents.get(saved.document.id)
    assert stored.file_id == "NEWPIC"
    assert stored.file_kind == AttachmentKind.PHOTO
    assert stored.note == "CMR kerak"


async def test_a_stranger_cannot_edit_someone_elses_document() -> None:
    world = World()
    saved = world.document(user_id=42)
    state = make_state(7)
    await state.set_state(EditDocument.note)
    await state.update_data(edit_document_id=saved.document.id)

    note = FakeMessage(user_id=7, text="hacked")
    await handle_edit_note(note, state, world.update_document)

    assert NOT_YOURS_MESSAGE in texts(note)
    assert world.documents.get(saved.document.id).note == "CMR kerak"


async def test_documented_places_lead_the_picker_and_wear_the_mark() -> None:
    world = World()
    bare = world.place(name="Hujjatsiz joy")
    documented = world.place(name="Hujjatli joy")
    world.add_document.execute(user_id=42, place_id=documented.id, note="CMR")
    state = make_state()

    start = FakeMessage()
    await handle_add_document_start(
        start,
        state,
        admin_ids=(),
        has_add_access=world.has_add_access,
        find_places=world.find_places,
        count_documents_by_place=world.count_documents_by_place,
    )

    keyboard = start.answers[0]["reply_markup"]
    labels = [row[0].text for row in keyboard.inline_keyboard]
    callbacks_ = [row[0].callback_data for row in keyboard.inline_keyboard]
    # The documented place rises to the top and says why.
    assert labels[0] == "📁 Hujjatli joy"
    assert callbacks_[0] == f"add_doc:place:{documented.id}"
    assert labels[1] == "Hujjatsiz joy"
    assert callbacks_[1] == f"add_doc:place:{bare.id}"


async def test_deleting_my_document_asks_then_deletes() -> None:
    from app.application.use_cases.documents import DeleteDocumentUseCase
    from app.presentation.telegram.handlers.documents import (
        handle_confirm_delete,
        handle_delete_prompt,
    )

    world = World()
    saved = world.document(user_id=42)

    prompt = FakeCallbackQuery(f"my_doc:delete:{saved.document.id}", user_id=42)
    await handle_delete_prompt(prompt)
    confirmation = prompt.message.answers[0]
    assert "o'chirasizmi" in str(confirmation["text"])
    data = [row[0].callback_data for row in confirmation["reply_markup"].inline_keyboard]
    assert data == [
        f"my_doc:confirm_delete:{saved.document.id}",
        "my_doc:cancel_delete",
    ]

    confirm = FakeCallbackQuery(f"my_doc:confirm_delete:{saved.document.id}", user_id=42)
    await handle_confirm_delete(confirm, DeleteDocumentUseCase(world.documents))

    assert world.documents.get(saved.document.id) is None
    assert "O'chirildi" in texts(confirm.message)


async def test_a_stranger_cannot_confirm_someone_elses_delete() -> None:
    from app.application.use_cases.documents import DeleteDocumentUseCase
    from app.presentation.telegram.handlers.documents import handle_confirm_delete

    world = World()
    saved = world.document(user_id=42)

    confirm = FakeCallbackQuery(f"my_doc:confirm_delete:{saved.document.id}", user_id=7)
    await handle_confirm_delete(confirm, DeleteDocumentUseCase(world.documents))

    assert world.documents.get(saved.document.id) is not None
    assert NOT_YOURS_MESSAGE in confirm.alerts


async def test_cancelling_the_delete_keeps_the_document() -> None:
    from app.presentation.telegram.handlers.documents import handle_cancel_delete

    world = World()
    saved = world.document(user_id=42)

    cancel = FakeCallbackQuery("my_doc:cancel_delete", user_id=42)
    await handle_cancel_delete(cancel)

    assert world.documents.get(saved.document.id) is not None
    assert "bekor" in texts(cancel.message).lower()
