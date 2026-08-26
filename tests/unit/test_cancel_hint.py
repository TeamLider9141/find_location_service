"""Every wizard prompt names the way out.

A driver stuck mid-flow — wrong button, wrong file, second thoughts — can only
use /cancel if the message in front of them says it exists.
"""

import pytest

from app.presentation.telegram.handlers import add_place, documents, find_place, my_places
from app.presentation.telegram.prompts import CANCEL_HINT, with_cancel_hint


def test_the_hint_lands_at_the_bottom() -> None:
    assert with_cancel_hint("Savol?").endswith(f"\n\n{CANCEL_HINT}")


@pytest.mark.parametrize(
    "prompt",
    [
        add_place.ASK_LOCATION_MESSAGE,
        add_place.ASK_LOCATION_AGAIN_MESSAGE,
        add_place.ASK_CATEGORY_MESSAGE,
        add_place.ASK_NAME_MESSAGE,
        add_place.BLANK_NAME_MESSAGE,
        add_place.ASK_NOTE_MESSAGE,
        my_places.ASK_NEW_NAME_MESSAGE,
        my_places.BLANK_NAME_MESSAGE,
        my_places.ASK_NEW_NOTE_MESSAGE,
        my_places.ASK_NEW_LOCATION_MESSAGE,
        my_places.NOT_A_LOCATION_MESSAGE,
        documents.ATTACH_PLACE_MESSAGE,
        documents.PLACE_CHOSEN_TEMPLATE,
        documents.FILE_RECEIVED_MESSAGE,
        documents.UNSUPPORTED_FILE_MESSAGE,
        documents.NOTE_TOO_LONG_TEMPLATE,
        documents.BLANK_NOTE_MESSAGE,
        documents.ASK_NEW_FILE_MESSAGE,
        documents.ASK_NEW_NOTE_MESSAGE,
        find_place.NEARBY_PROMPT_TEMPLATE,
        find_place.NOT_A_LOCATION_MESSAGE,
    ],
)
def test_every_flow_prompt_carries_the_cancel_hint(prompt: str) -> None:
    assert CANCEL_HINT in prompt
