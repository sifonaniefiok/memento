"""Turn Markdown text into flashcards.

The file format is deliberately tiny so it stays readable without Memento:

    # Git basics                    <- optional deck title (else the file name)

    ## What does `git add -p` do?   <- a level-2 heading is a question
    tags: git, staging              <- optional, must be the first line of the body

    Stages changes hunk by hunk.    <- everything after it is the answer

    ---                             <- optional: ends the card explicitly

Rules, in the order the parser applies them:

* Lines inside fenced code blocks (``` or ~~~) are never structural, so a
  ``## comment`` inside a code sample does not start a new card.
* A level-2 heading (``## ...``) starts a new card and ends the previous one.
* A level-1 heading (``# ...``) ends the current card. The first one that
  appears before any card is the deck title.
* A thematic break (``---``, ``***`` or ``___``) ends the current card. Text
  after it and before the next ``##`` is a free-form note and is ignored.
* Text before the first card (an introduction) is ignored.
* A YAML front-matter block at the very top of the file is skipped.

The parser is pure: it takes a string and returns data, it never touches the
disk or the database. That keeps it easy to test against odd inputs.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

# An ATX heading: up to 3 spaces of indentation, 1-6 '#', then a space (or end of
# line). Optional closing '#'s are dropped, as CommonMark does.
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)(?:[ \t]+#+)?[ \t]*$")
# Start of a fenced code block: 3+ backticks or tildes. Group 1 is the fence.
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
# A line made of 3+ '-', '*' or '_' (optionally spaced): a Markdown thematic break.
_THEMATIC_BREAK = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_TAGS = re.compile(r"^\s*tags\s*:(.*)$", re.IGNORECASE)


def normalize_question(question: str) -> str:
    """Reduce a question to the form used for its identity.

    Unicode is NFC-normalised (so "é" typed two different ways is the same),
    case is folded and runs of whitespace collapse to one space. That means
    fixing capitalisation or spacing in a question keeps its review history,
    while actually rewording it creates a new card.
    """
    text = unicodedata.normalize("NFC", question)
    return " ".join(text.casefold().split())


def card_id(source: str, question: str) -> str:
    """A stable identifier for a card: a hash of its file and normalised question.

    The id is what links a card in Markdown to its scheduling row in SQLite.
    Nothing is written back into the Markdown, so the file stays clean. 16 hex
    characters (64 bits) is plenty to avoid collisions in a personal deck.
    """
    key = f"{source}\n{normalize_question(question)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Card:
    """One question/answer pair, as written in a Markdown file."""

    question: str
    answer: str
    source: str
    """Path of the file relative to the deck directory, with '/' separators."""
    title: str
    """The deck title: the file's ``# Title`` or, failing that, its name."""
    line: int
    """1-based line number of the question heading, for error messages."""
    tags: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return card_id(self.source, self.question)


@dataclass(frozen=True)
class Problem:
    """Something wrong in a file that ``memento check`` should report."""

    line: int
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ParsedFile:
    """The result of parsing one Markdown file."""

    source: str
    title: str
    cards: list[Card] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


@dataclass
class _Draft:
    """A card while its body is still being collected."""

    question: str
    line: int
    body: list[str] = field(default_factory=list)


def _skip_front_matter(lines: list[str]) -> int:
    """Return the index of the first line after a leading YAML front-matter block."""
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return index + 1
    return 0  # No closing marker: it was just a thematic break, not front matter.


def _split_tags(body: list[str]) -> tuple[tuple[str, ...], list[str]]:
    """Pull an optional ``tags: a, b`` line off the top of a card body."""
    for index, line in enumerate(body):
        if not line.strip():
            continue
        match = _TAGS.match(line)
        if not match:
            break
        tags = tuple(
            tag.strip().lstrip("#") for tag in match.group(1).split(",") if tag.strip().lstrip("#")
        )
        return tags, body[index + 1 :]
    return (), body


def _trim_blank_lines(lines: list[str]) -> str:
    """Join lines, dropping blank lines at the start and end but keeping indentation."""
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end])


def parse_markdown(text: str, source: str, default_title: str) -> ParsedFile:
    """Parse the text of one Markdown file into cards.

    ``source`` is stored on every card (it is part of the card's identity) and
    ``default_title`` is used when the file has no ``# Title`` heading.
    """
    # splitlines() understands \n, \r\n and \r, so Windows files parse the same.
    lines = text.removeprefix("﻿").splitlines()
    result = ParsedFile(source=source, title=default_title)
    title: str | None = None
    draft: _Draft | None = None
    fence: str | None = None  # The opening fence, e.g. "```", while inside a code block.
    fence_line = 0

    def finish() -> None:
        nonlocal draft
        if draft is None:
            return
        tags, body = _split_tags(draft.body)
        answer = _trim_blank_lines(body)
        if not answer:
            result.problems.append(Problem(draft.line, f"card has no answer: {draft.question!r}"))
        result.cards.append(
            Card(
                question=draft.question,
                answer=answer,
                source=source,
                title=title or default_title,
                line=draft.line,
                tags=tags,
            )
        )
        draft = None

    start = _skip_front_matter(lines)
    for lineno, line in enumerate(lines[start:], start=start + 1):
        if fence is not None:
            # Inside a code block only a matching closing fence matters: same
            # character, at least as long, and nothing else on the line.
            stripped = line.strip()
            if (
                len(line) - len(line.lstrip(" ")) <= 3
                and stripped
                and set(stripped) == {fence[0]}
                and len(stripped) >= len(fence)
            ):
                fence = None
            if draft is not None:
                draft.body.append(line)
            continue

        fence_match = _FENCE_OPEN.match(line)
        if fence_match and not (fence_match.group(1)[0] == "`" and "`" in fence_match.group(2)):
            fence, fence_line = fence_match.group(1), lineno
            if draft is not None:
                draft.body.append(line)
            continue

        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) <= 2:
            finish()
            heading_text = heading.group(2).strip()
            if len(heading.group(1)) == 1:
                if title is None and not result.cards:
                    title = heading_text or None
            elif not heading_text:
                result.problems.append(Problem(lineno, "'##' heading with no question text"))
            else:
                draft = _Draft(question=heading_text, line=lineno)
            continue

        if _THEMATIC_BREAK.match(line):
            finish()
            continue

        if draft is not None:
            draft.body.append(line)

    finish()
    if fence is not None:
        result.problems.append(
            Problem(fence_line, f"code block opened with {fence} is never closed", "warning")
        )
    result.title = title or default_title
    return result
