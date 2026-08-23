import re

_LATIN_RE = re.compile(r"[A-Za-z]")
_MARKDOWN_EDGE_CHARS = "*_`\"'“”‘’"

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


def clean_search_query(query: str) -> str:
    return query.strip().strip(_MARKDOWN_EDGE_CHARS).strip()


def build_search_query_candidates(query: str) -> list[str]:
    cleaned_query = clean_search_query(query)
    if not cleaned_query:
        return []

    candidates = [cleaned_query]
    cyrillic_query = transliterate_latin_russian_to_cyrillic(cleaned_query)
    if cyrillic_query and cyrillic_query != cleaned_query:
        candidates.append(cyrillic_query)

    return candidates


def transliterate_latin_russian_to_cyrillic(query: str) -> str | None:
    if _LATIN_RE.search(query) is None:
        return None

    normalized = query.lower()
    output: list[str] = []
    index = 0
    while index < len(normalized):
        for size in (3, 2):
            chunk = normalized[index : index + size]
            if chunk in _DIGRAPHS:
                output.append(_DIGRAPHS[chunk])
                index += size
                break
        else:
            char = normalized[index]
            output.append(_LETTERS.get(char, char))
            index += 1

    return "".join(output)
