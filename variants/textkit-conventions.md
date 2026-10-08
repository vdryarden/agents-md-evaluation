# Agent instructions

## House conventions

- Every new public function goes in its own module under `textkit/`, named after the feature (for example `textkit/slug.py`).
- Export every public function from `textkit/__init__.py` and keep `__all__` sorted alphabetically.
- Public functions need a docstring and full type hints.
- Add tests for new code in `tests/test_<module>.py`.
- Add a line to `CHANGELOG.md` under `## Unreleased` for every user-visible change.

## Workflow

Run `python -m pytest -q` before you finish.
