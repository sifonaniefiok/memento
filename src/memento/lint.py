"""``memento check``: find mistakes in the Markdown before they bite during review.

Kept separate from the parser on purpose: the parser is lenient (it should
load a slightly broken file rather than refuse to start a review) while the
linter is strict and tells you exactly what to fix and where.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from memento.deck import Deck
from memento.parser import Card, normalize_question


@dataclass(frozen=True, order=True)
class Issue:
    source: str
    line: int
    severity: str  # "error" or "warning"
    message: str

    def __str__(self) -> str:
        return f"{self.source}:{self.line}: {self.severity}: {self.message}"


def check_deck(deck: Deck) -> list[Issue]:
    """Return every issue in the deck, sorted by file and line."""
    issues: list[Issue] = []

    for parsed in deck.files:
        for problem in parsed.problems:
            issues.append(Issue(parsed.source, problem.line, problem.severity, problem.message))
        if not parsed.cards:
            issues.append(
                Issue(parsed.source, 1, "warning", "no cards found (questions use '## ' headings)")
            )

    # Same question twice in one file: both cards get the same id and would
    # share a schedule, so only the first is ever reviewed. That is an error.
    by_id: dict[str, list[Card]] = defaultdict(list)
    for card in deck.all_cards:
        by_id[card.id].append(card)
    for cards in by_id.values():
        first = cards[0]
        for duplicate in cards[1:]:
            issues.append(
                Issue(
                    duplicate.source,
                    duplicate.line,
                    "error",
                    f"duplicate question {duplicate.question!r} (first on line {first.line})",
                )
            )

    # Same question in different files is allowed (they are separate cards)
    # but is usually a copy-paste accident, so it is only a warning.
    by_question: dict[str, list[Card]] = defaultdict(list)
    for card in deck.cards:
        by_question[normalize_question(card.question)].append(card)
    for cards in by_question.values():
        for other in cards[1:]:
            issues.append(
                Issue(
                    other.source,
                    other.line,
                    "warning",
                    f"question {other.question!r} also appears in "
                    f"{cards[0].source}:{cards[0].line}",
                )
            )

    return sorted(issues)
