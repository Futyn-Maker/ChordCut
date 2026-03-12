"""Text utilities for ChordCut."""

import unicodedata


def normalize_search(text: str) -> str:
    """Normalize *text* for search matching.

    Applies, in order:
    1. Unicode case-folding (casefold handles ß→ss, etc.)
    2. NFD decomposition (splits accented chars into base + combining mark)
    3. Stripping of combining diacritical marks (removes accents)
    4. Russian ё→е equivalence
    """
    text = text.casefold()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("ё", "е")
    return text
