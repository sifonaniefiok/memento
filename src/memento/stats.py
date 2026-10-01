"""Statistics for ``memento stats``.

:func:`compute_stats` is pure (cards, states and history in, numbers out) so the
numbers can be unit-tested; :func:`render_stats` only draws them with rich.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from rich.console import Console
from rich.table import Table

from memento.parser import Card
from memento.scheduler import CardState
from memento.store import ReviewLog

MATURE_DAYS = 21
"""A card whose interval reached 3 weeks is considered well learned ("mature")."""
RETENTION_WINDOW_DAYS = 30
FORECAST_DAYS = 7


@dataclass(frozen=True)
class Stats:
    total: int
    new: int
    """Never reviewed."""
    learned: int
    """Reviewed at least once."""
    mature: int
    """Learned cards whose interval is at least MATURE_DAYS."""
    due_today: int
    """Learned cards due today or overdue (new cards are counted separately)."""
    reviews_today: int
    retention: float | None
    """Share of recall attempts passed in the last RETENTION_WINDOW_DAYS, 0-1."""
    retention_sample: int
    streak: int
    """Consecutive days with at least one review, ending today or yesterday."""
    average_ease: float | None
    forecast: list[tuple[date, int]]
    """(day, cards due) for the next FORECAST_DAYS days; today includes overdue cards."""


def current_streak(review_days: Iterable[date], today: date) -> int:
    """Count consecutive review days ending today.

    If you have not reviewed *yet* today, a streak that ended yesterday still
    counts - it is not broken until the day is over.
    """
    days = set(review_days)
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def compute_stats(
    cards: Sequence[Card],
    states: Mapping[str, CardState],
    reviews: Sequence[ReviewLog],
    today: date,
) -> Stats:
    """Summarise the deck. Only cards present in the Markdown are counted;
    the review history (retention, streak) covers every review ever logged."""
    current = [states[card.id] for card in cards if card.id in states]

    # Retention only looks at *recall attempts*: reviews of cards that had
    # already been learned (interval_before > 0). A brand-new card cannot be
    # "remembered", so including first views would skew the number.
    window_start = today - timedelta(days=RETENTION_WINDOW_DAYS - 1)
    attempts = [r for r in reviews if r.review_date >= window_start and r.interval_before > 0]
    passed = sum(1 for r in attempts if r.quality >= 3)

    forecast = []
    for offset in range(FORECAST_DAYS):
        day = today + timedelta(days=offset)
        if offset == 0:
            count = sum(1 for s in current if s.due <= day)
        else:
            count = sum(1 for s in current if s.due == day)
        forecast.append((day, count))

    return Stats(
        total=len(cards),
        new=len(cards) - len(current),
        learned=len(current),
        mature=sum(1 for s in current if s.schedule.interval >= MATURE_DAYS),
        due_today=forecast[0][1],
        reviews_today=sum(1 for r in reviews if r.review_date == today),
        retention=passed / len(attempts) if attempts else None,
        retention_sample=len(attempts),
        streak=current_streak((r.review_date for r in reviews), today),
        average_ease=(sum(s.schedule.ease for s in current) / len(current) if current else None),
        forecast=forecast,
    )


def render_stats(stats: Stats, console: Console) -> None:
    """Draw the overview table and the 7-day forecast."""
    overview = Table(title="Memento stats", show_header=False, title_justify="left")
    overview.add_column("Metric")
    overview.add_column("Value", justify="right")
    overview.add_row("Cards", str(stats.total))
    overview.add_row("New (never reviewed)", str(stats.new))
    overview.add_row("Learned", str(stats.learned))
    overview.add_row(f"  of which mature (interval >= {MATURE_DAYS}d)", str(stats.mature))
    overview.add_row("Due today", str(stats.due_today))
    overview.add_row("Reviews today", str(stats.reviews_today))
    if stats.retention is None:
        retention = "-"
    else:
        passed = round(stats.retention * stats.retention_sample)
        retention = f"{stats.retention:.0%} ({passed} of {stats.retention_sample})"
    overview.add_row(f"Retention (last {RETENTION_WINDOW_DAYS} days)", retention)
    overview.add_row("Streak", f"{stats.streak} day{'s' if stats.streak != 1 else ''}")
    ease = "-" if stats.average_ease is None else f"{stats.average_ease:.2f}"
    overview.add_row("Average ease", ease)
    console.print(overview)

    forecast = Table(title=f"Next {FORECAST_DAYS} days", title_justify="left")
    forecast.add_column("Day")
    forecast.add_column("Due", justify="right")
    forecast.add_column("")
    peak = max((count for _, count in stats.forecast), default=0) or 1
    for offset, (day, count) in enumerate(stats.forecast):
        label = "Today" if offset == 0 else day.strftime("%a %d %b")
        bar = "█" * round(20 * count / peak) if count else ""
        forecast.add_row(label, str(count), f"[green]{bar}[/]")
    console.print(forecast)
