#!/bin/bash
set -e
cd /app
cat > textkit/slug.py <<'PY'
import re


def slugify(text: str) -> str:
    """Lowercase text and join its ASCII alphanumeric runs with hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
PY
cat > textkit/__init__.py <<'PY'
from textkit.case import title_case
from textkit.slug import slugify
from textkit.whitespace import collapse_spaces

__all__ = ["collapse_spaces", "slugify", "title_case"]
PY
cat > tests/test_slug.py <<'PY'
from textkit import slugify


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
PY
python - <<'PY'
import pathlib
p = pathlib.Path("CHANGELOG.md")
p.write_text(p.read_text().replace("## Unreleased\n", "## Unreleased\n\n- Add `slugify`.\n", 1))
PY
