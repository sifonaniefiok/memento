"""The SM-2 spaced-repetition algorithm, as pure functions.

SM-2 was published by Piotr Wozniak in 1987 for SuperMemo and is still the core
of many flashcard apps. Each card carries three numbers:

* ``repetitions`` - how many times in a row it was recalled correctly,
* ``ease`` - the "easiness factor", how fast its interval grows (starts at 2.5),
* ``interval`` - how many days to wait before showing it again.

After every review you grade your recall with a *quality* from 0 to 5:

* quality >= 3 (a pass): the interval grows - 1 day, then 6 days, then the
  previous interval multiplied by the ease factor.
* quality < 3 (a fail): repetitions reset to 0 and the card comes back tomorrow.

Either way the ease factor is nudged by
``0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)``: +0.10 for a perfect 5, unchanged
for a 4, -0.14 for a 3, and so on, but never below 1.3 so a hard card does not
end up being shown every single day forever.

This module knows nothing about files, databases or dates on a calendar, which
is why its tests can check the exact numbers of a known sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

DEFAULT_EASE = 2.5
MIN_EASE = 1.3


class Grade(IntEnum):
    """The four buttons shown during review (friendlier than six quality levels)."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4

    @property
    def quality(self) -> int:
        """The SM-2 quality (0-5) this button stands for."""
        return _GRADE_QUALITY[self]

    @property
    def label(self) -> str:
        return self.name.capitalize()


# AGAIN is a fail ("I didn't remember it"). HARD, GOOD and EASY are passes with
# decreasing effort, mapping to SM-2's 3 ("correct with serious difficulty"),
# 4 ("correct after hesitation") and 5 ("perfect response").
_GRADE_QUALITY = {Grade.AGAIN: 1, Grade.HARD: 3, Grade.GOOD: 4, Grade.EASY: 5}


@dataclass(frozen=True)
class Schedule:
    """The SM-2 state of one card. A never-reviewed card is ``Schedule()``."""

    repetitions: int = 0
    ease: float = DEFAULT_EASE
    interval: int = 0


def _round_half_up(value: float) -> int:
    """Round 7.5 to 8. Python's round() would give 8 here but 6.5 -> 6 ("banker's
    rounding"), which would make intervals surprising to explain."""
    return int(value + 0.5)


def next_ease(ease: float, quality: int) -> float:
    """Apply SM-2's ease-factor update for one review, clamped at MIN_EASE."""
    q = 5 - quality
    updated = ease + (0.1 - q * (0.08 + q * 0.02))
    # Round away floating-point noise (2.5 + 0.1 = 2.6000000000000001).
    return max(MIN_EASE, round(updated, 4))


def review(schedule: Schedule, quality: int) -> Schedule:
    """Return the card's new schedule after a review graded ``quality`` (0-5).

    The new interval is computed with the ease factor the card had *before* this
    review, then the ease factor is updated - the order given in the SM-2 paper.
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"SM-2 quality must be between 0 and 5, got {quality}")

    if quality >= 3:
        if schedule.repetitions == 0:
            interval = 1
        elif schedule.repetitions == 1:
            interval = 6
        else:
            interval = _round_half_up(schedule.interval * schedule.ease)
        repetitions = schedule.repetitions + 1
    else:
        repetitions = 0
        interval = 1

    return Schedule(
        repetitions=repetitions,
        ease=next_ease(schedule.ease, quality),
        interval=interval,
    )
