"""Shared fixtures: a frozen clock, a throwaway deck and a console that records output."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from rich.console import Console

from memento.clock import FixedClock

GIT_DECK = """\
# Git

## How do you stage part of a file?
tags: git

git add -p

---

## What does git stash do?

Saves uncommitted changes on a stack.
"""

PYTHON_DECK = """\
# Python

## What is a list comprehension?

`[x * x for x in range(3)]`

## What does `is` compare?

Identity.
"""


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))


@pytest.fixture
def deck_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "deck"
    directory.mkdir()
    (directory / "git.md").write_text(GIT_DECK, encoding="utf-8")
    (directory / "python.md").write_text(PYTHON_DECK, encoding="utf-8")
    return directory


@pytest.fixture
def console() -> Console:
    """A plain-text console whose output can be read back with ``.file.getvalue()``."""
    return Console(file=io.StringIO(), width=100, color_system=None, highlight=False)


def output(console: Console) -> str:
    return console.file.getvalue()  # type: ignore[attr-defined]


def scripted_keys(*presses: str) -> Callable[[], str]:
    """A key reader that replays ``presses`` and then reports end of input ("")."""
    remaining = iter(presses)
    return lambda: next(remaining, "")
