# Agent instructions

## Before you change anything

- Read the files next to the one you will change. Find one existing feature that looks like yours and copy how it is built: where its code lives, how it is named, exported, typed, documented and tested.
- Look for project bookkeeping and keep it current: `CHANGELOG.md`, `__all__` or index files, docs, config. If the repo updates it for similar changes, update it for yours.

## While you work

- Make the smallest change that fully solves the task. Don't add options, abstractions or dependencies nobody asked for.
- Add or update tests for new behavior, in the same place and style as the existing tests.
- Follow the repo's style over your own habits, including ordering, naming and type hints.

## Before you finish

- Run the project's test command (look in the README, `pyproject.toml`, `package.json` or `Makefile`) and fix what fails.
- Check `git status` and `git diff`: no stray files, debug prints or unrelated edits.
