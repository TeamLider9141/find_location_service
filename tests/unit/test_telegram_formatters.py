from app.presentation.telegram.formatters import format_start_message


def test_start_message_describes_the_shared_database() -> None:
    text = format_start_message()

    assert "manzil" in text.lower()
    assert "Домодедово аэропорт" in text


def test_start_message_lists_every_entry_point() -> None:
    text = format_start_message()

    for hint in (
        "Manzillar",
        "Manzildagi hujjatlar",
        "Yaqin atrofda",
        "Joy qo'shish",
        "Mening ma'lumotlarim",
        "Sozlamalar",
    ):
        assert hint in text
