import re


def collapse_spaces(text: str) -> str:
    """Replace runs of whitespace with one space and trim the ends."""
    return re.sub(r"\s+", " ", text).strip()
