"""Text normalization helpers."""

from typing import Optional

_DASH_VARIANTS = (
    "\u2010",  # hyphen
    "\u2011",  # non-breaking hyphen
    "\u2012",  # figure dash
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\u2015",  # horizontal bar
    "\u2212",  # minus sign
    "\u30fc",  # katakana-hiragana prolonged sound mark
    "\uff0d",  # fullwidth hyphen-minus
)


def normalize_title(value: Optional[str]) -> str:
    """Normalize window titles for robust matching."""
    if value is None:
        return ""
    text = str(value)
    for dash in _DASH_VARIANTS:
        text = text.replace(dash, "-")
    # Collapse whitespace and compare case-insensitively.
    return " ".join(text.strip().split()).casefold()
