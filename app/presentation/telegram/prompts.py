"""The one hint every wizard prompt carries.

A driver stuck mid-flow — wrong button, wrong file, second thoughts — has one
way out, and it is only useful if the message in front of them names it.
"""

CANCEL_HINT = "Xato bo'lsa — /cancel bosing."


def with_cancel_hint(text: str) -> str:
    return f"{text}\n\n{CANCEL_HINT}"
