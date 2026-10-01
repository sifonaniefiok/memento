"""Writing new cards into Markdown files (``memento add``).

Appending text to a Markdown file is easy; appending it *safely* is the
interesting part. An answer containing a line like ``## Notes`` or ``---``
outside a code block would silently split into two cards. So every append is
verified by parsing the file before and after: if the result is not exactly
"the old cards plus the new ones", nothing is written.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from memento.deck import source_name
from memento.parser import parse_markdown


class AddError(Exception):
    """The card could not be added; the message says why."""


@dataclass(frozen=True)
class NewCard:
    question: str
    answer: str
    tags: tuple[str, ...] = ()


def resolve_card_file(deck_dir: Path, name: str) -> Path:
    """Map ``git`` or ``topics/git.md`` to a file inside the deck directory.

    Refuses paths that escape the deck, because cards outside it would never
    be found by ``review``.
    """
    if not name.endswith(".md"):
        name += ".md"
    path = (deck_dir / name).resolve()
    if not path.is_relative_to(deck_dir.resolve()):
        raise AddError(f"{name} is outside the deck directory {deck_dir}")
    return path


def title_from_filename(path: Path) -> str:
    """``python-basics.md`` -> ``Python Basics`` for a brand-new file's heading."""
    return path.stem.replace("-", " ").replace("_", " ").title()


def format_card(card: NewCard) -> str:
    """Render one card in Memento's Markdown format."""
    question = card.question.strip()
    if not question:
        raise AddError("the question is empty")
    if "\n" in question or "\r" in question:
        raise AddError("the question must be a single line (it becomes a '## ' heading)")
    answer = card.answer.strip("\n")
    if not answer.strip():
        raise AddError(f"the answer to {question!r} is empty")
    lines = [f"## {question}"]
    if card.tags:
        lines.append("tags: " + ", ".join(card.tags))
    lines += ["", answer, ""]
    return "\n".join(lines)


def append_cards(path: Path, deck_dir: Path, cards: Sequence[NewCard]) -> None:
    """Append ``cards`` to ``path`` (creating it with a title if needed), safely."""
    if not cards:
        raise AddError("no cards to add")
    source = source_name(path, deck_dir.resolve())
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    before = parse_markdown(existing, source, path.stem)

    known = {card.id for card in before.cards}
    if not existing.strip():
        existing = f"# {title_from_filename(path)}\n"
    blocks = []
    for card in cards:
        blocks.append(format_card(card))
    updated = existing.rstrip("\n") + "\n\n" + "\n".join(blocks)

    after = parse_markdown(updated, source, path.stem)
    added = after.cards[len(before.cards) :]
    expected = [(c.question.strip(), c.answer.strip("\n").strip(), tuple(c.tags)) for c in cards]
    actual = [(c.question, c.answer.strip(), c.tags) for c in added]
    if after.cards[: len(before.cards)] != before.cards or actual != expected:
        raise AddError(
            "the new card would not parse back as written - an answer probably contains "
            "a '#'/'##' heading or a '---' line outside a code block, or the file "
            "ends inside an unclosed code block. Nothing was written."
        )
    for card in added:
        if card.id in known:
            raise AddError(f"{path.name} already has the question {card.question!r}")
        known.add(card.id)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


EDITOR_TEMPLATE = """\
Write one or more cards below, then save and close the editor.
Anything above the first '## ' question is ignored. Leave no question to cancel.

## {question}

{answer}
"""


def editor_command() -> list[str]:
    """The user's editor from $VISUAL or $EDITOR (may include arguments)."""
    command = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not command:
        command = "notepad" if os.name == "nt" else "vi"
    return shlex.split(command)


def cards_from_editor(question: str = "", answer: str = "") -> list[NewCard]:
    """Open $EDITOR on a template and return the cards written in it."""
    with tempfile.TemporaryDirectory() as tmp:
        draft = Path(tmp) / "new-card.md"
        draft.write_text(EDITOR_TEMPLATE.format(question=question, answer=answer), "utf-8")
        try:
            result = subprocess.run([*editor_command(), str(draft)], check=False)
        except FileNotFoundError as exc:
            raise AddError(f"could not start the editor: {exc}") from exc
        if result.returncode != 0:
            raise AddError(f"the editor exited with status {result.returncode}; nothing added")
        parsed = parse_markdown(draft.read_text("utf-8"), "draft.md", "draft")
    return [NewCard(card.question, card.answer, card.tags) for card in parsed.cards]
