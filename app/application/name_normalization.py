import re

_LATIN_RE = re.compile(r"[A-Za-z]")
_WHITESPACE_RE = re.compile(r"\s+")

_DIGRAPHS: dict[str, str] = {
    "sch": "щ",
    "shh": "щ",
    "yo": "ё",
    "yu": "ю",
    "ya": "я",
    "ye": "е",
    "zh": "ж",
    "kh": "х",
    "ts": "ц",
    "ch": "ч",
    "sh": "ш",
}

_LETTERS: dict[str, str] = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "ы",
    "z": "з",
}


def normalize_name(name: str) -> str:
    """Return the search key for a place name.

    Lowercases, collapses whitespace and transliterates Latin spellings into
    Cyrillic, so that "Gazprom" and "Газпром" share one key.
    """
    collapsed = _WHITESPACE_RE.sub(" ", name.strip()).lower()
    if not collapsed:
        return ""
    return _transliterate(collapsed)


def _transliterate(value: str) -> str:
    if _LATIN_RE.search(value) is None:
        return value

    output: list[str] = []
    index = 0
    while index < len(value):
        for size in (3, 2):
            chunk = value[index : index + size]
            if chunk in _DIGRAPHS:
                output.append(_DIGRAPHS[chunk])
                index += size
                break
        else:
            output.append(_LETTERS.get(value[index], value[index]))
            index += 1

    return "".join(output)
