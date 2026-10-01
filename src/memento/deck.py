"""Finding and loading the Markdown files in a deck directory.

A *deck directory* (``~/memento`` by default) holds any number of ``.md``
files, in sub-folders if you like. Each file is one deck with its own title.
The Markdown files are the single source of truth for *what* the cards are;
the SQLite database next to them only remembers *when* to show them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from memento.parser import Card, ParsedFile, parse_markdown

DB_FILENAME = ".memento.db"
ENV_VAR = "MEMENTO_DECK"


def default_deck_dir() -> Path:
    """Where cards live when no ``--deck`` is given: $MEMENTO_DECK, else ~/memento."""
    env = os.environ.get(ENV_VAR)
    return Path(env).expanduser() if env else Path.home() / "memento"


def markdown_files(deck_dir: Path) -> list[Path]:
    """All ``.md`` files under the deck directory, in a stable (sorted) order.

    Hidden files and folders (``.git``, ``.obsidian`` ...) are skipped so a deck
    can live inside a git repository or a notes vault.
    """
    files = []
    for path in deck_dir.rglob("*.md"):
        relative = path.relative_to(deck_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(deck_dir).as_posix())


def source_name(path: Path, deck_dir: Path) -> str:
    """The deck-relative, '/'-separated name used in card ids (same on every OS)."""
    try:
        return path.relative_to(deck_dir).as_posix()
    except ValueError:  # e.g. one path is absolute and the other relative
        return path.resolve().relative_to(deck_dir.resolve()).as_posix()


def parse_file(path: Path, deck_dir: Path) -> ParsedFile:
    """Read and parse one Markdown file in the deck."""
    text = path.read_text(encoding="utf-8")
    return parse_markdown(text, source=source_name(path, deck_dir), default_title=path.stem)


@dataclass
class Deck:
    """Every parsed file in a deck directory."""

    directory: Path
    files: list[ParsedFile] = field(default_factory=list)

    @property
    def db_path(self) -> Path:
        return self.directory / DB_FILENAME

    @property
    def all_cards(self) -> list[Card]:
        """Every card in file order, including duplicates (``check`` reports those)."""
        return [card for parsed in self.files for card in parsed.cards]

    @property
    def cards(self) -> list[Card]:
        """Cards with duplicates removed: the first card with a given id wins.

        Two cards with the same question in the same file would share one
        scheduling row, so only the first is reviewed until the user fixes it.
        """
        seen: set[str] = set()
        unique = []
        for card in self.all_cards:
            if card.id not in seen:
                seen.add(card.id)
                unique.append(card)
        return unique

    def filter(self, pattern: str | None) -> list[Card]:
        """Cards whose file name or deck title contains ``pattern`` (case-insensitive)."""
        if not pattern:
            return self.cards
        needle = pattern.casefold()
        return [
            card
            for card in self.cards
            if needle in card.source.casefold() or needle in card.title.casefold()
        ]


def load_deck(deck_dir: Path) -> Deck:
    """Parse every Markdown file in ``deck_dir``."""
    return Deck(
        directory=deck_dir,
        files=[parse_file(path, deck_dir) for path in markdown_files(deck_dir)],
    )
