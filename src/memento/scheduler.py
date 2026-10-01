"""Deciding which cards to show and what happens when one is graded.

This is the glue between the pure SM-2 maths (:mod:`memento.sm2`) and the
calendar: it turns "interval = 6" into "due on 2026-10-07" and picks which
cards make up today's review session. Like ``sm2`` it is pure - it takes
states in and returns states out - so the CLI and the review session do the
saving.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from memento import sm2
from memento.parser import Card


@dataclass(frozen=True)
class CardState:
    """What the database remembers about a card that has been reviewed at least once.

    Cards that were never reviewed have *no* state at all: that is what "new" means.
    """

    card_id: str
    schedule: sm2.Schedule
    due: date
    last_reviewed: date
    lapses: int = 0
    """How many times the card was forgotten after having been learned."""


def is_due(state: CardState, today: date) -> bool:
    """A card is due on its due date and every day after it until reviewed."""
    return state.due <= today


def apply_grade(
    card_id: str, previous: CardState | None, grade: sm2.Grade, today: date
) -> CardState:
    """Return the card's state after being graded ``grade`` on ``today``."""
    schedule = previous.schedule if previous else sm2.Schedule()
    updated = sm2.review(schedule, grade.quality)
    forgot_learned_card = previous is not None and schedule.repetitions > 0 and grade.quality < 3
    return CardState(
        card_id=card_id,
        schedule=updated,
        due=today + timedelta(days=updated.interval),
        last_reviewed=today,
        lapses=(previous.lapses if previous else 0) + int(forgot_learned_card),
    )


def due_cards(cards: Iterable[Card], states: Mapping[str, CardState], today: date) -> list[Card]:
    """Reviewed cards that are due, most overdue first (ties keep file order)."""
    due = [card for card in cards if card.id in states and is_due(states[card.id], today)]
    return sorted(due, key=lambda card: states[card.id].due)


def new_cards(cards: Iterable[Card], states: Mapping[str, CardState]) -> list[Card]:
    """Cards that have never been reviewed, in file order."""
    return [card for card in cards if card.id not in states]


def build_queue(
    cards: Iterable[Card],
    states: Mapping[str, CardState],
    today: date,
    *,
    limit: int,
    new_per_day: int,
    new_seen_today: int = 0,
) -> list[Card]:
    """Choose the cards for one review session.

    Due reviews come first because falling behind on them is what makes people
    abandon spaced repetition. New cards fill the rest, capped per *day* (not
    per session) so running ``memento review`` twice does not double the
    number of new cards learned. ``limit`` caps the whole session.
    """
    cards = list(cards)
    new_allowance = max(0, new_per_day - new_seen_today)
    queue = due_cards(cards, states, today) + new_cards(cards, states)[:new_allowance]
    return queue[: max(0, limit)]
