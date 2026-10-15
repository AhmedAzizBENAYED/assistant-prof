"""French typography as teachers' word processors produce it."""

NBSP = "\u00a0"
"""No-break space: Word's French autocorrect puts it before ``:`` and inside guillemets."""

NNBSP = "\u202f"
"""Narrow no-break space: before ``;``, ``?`` and ``!``."""

APOSTROPHE = "\u2019"
"""Typographic apostrophe."""

_REPLACEMENTS = (
    (" :", NBSP + ":"),
    (" ;", NNBSP + ";"),
    (" ?", NNBSP + "?"),
    (" !", NNBSP + "!"),
    ("« ", "«" + NBSP),
    (" »", NBSP + "»"),
    ("'", APOSTROPHE),
)


def fr(text: str) -> str:
    """Apply French typography: no-break spaces before ``: ; ? !`` and in guillemets, curly '.

    Source strings are written with plain spaces and ASCII apostrophes for readability.
    """
    for plain, typographic in _REPLACEMENTS:
        text = text.replace(plain, typographic)
    return text
