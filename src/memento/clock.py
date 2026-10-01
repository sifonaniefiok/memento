"""Time sources.

Everything in Memento that needs "now" or "today" asks a :class:`Clock` instead of
calling ``datetime.now()`` directly. Spaced repetition is all about dates ("is this
card due today?"), so being able to pin the date makes the scheduler, the review
session and the statistics fully deterministic in tests.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Anything that can tell the current local time."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware datetime."""
        ...


def today(clock: Clock) -> date:
    """The calendar day, in the user's local time zone, that the clock is on."""
    return clock.now().date()


class SystemClock:
    """The real clock, in the machine's local time zone.

    Local time matters: a review done at 23:30 should count toward *today's*
    streak for the user, not tomorrow's UTC date.
    """

    def now(self) -> datetime:
        return datetime.now().astimezone()


class FixedClock:
    """A clock that only moves when told to. Used by tests (and handy for demos)."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            start = start.astimezone()
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None:
        """Move time forward, e.g. to simulate coming back to review tomorrow."""
        self._now += timedelta(days=days, hours=hours, minutes=minutes)
