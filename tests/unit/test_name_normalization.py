from app.application.name_normalization import normalize_name


def test_normalize_lowercases_and_trims() -> None:
    assert normalize_name("  Газпром  ") == "газпром"


def test_normalize_transliterates_latin_to_cyrillic() -> None:
    assert normalize_name("Gazprom") == "газпром"


def test_latin_and_cyrillic_spellings_normalize_to_the_same_value() -> None:
    assert normalize_name("Lukoil") == normalize_name("Лукоил")


def test_normalize_handles_digraphs() -> None:
    assert normalize_name("Shell") == "шелл"


def test_normalize_collapses_inner_whitespace() -> None:
    assert normalize_name("Кафе   У   Дороги") == "кафе у дороги"


def test_normalize_of_empty_string_is_empty() -> None:
    assert normalize_name("   ") == ""
