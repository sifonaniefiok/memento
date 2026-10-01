from datetime import date, datetime, timedelta

from conftest import output
from memento.parser import Card
from memento.scheduler import CardState
from memento.sm2 import Grade, Schedule
from memento.stats import compute_stats, current_streak, render_stats
from memento.store import ReviewLog

TODAY = date(2026, 1, 10)


def days(n: int) -> date:
    return TODAY + timedelta(days=n)


def log(day: date, grade: Grade, interval_before: int, card_id: str = "x") -> ReviewLog:
    return ReviewLog(
        card_id=card_id,
        reviewed_at=datetime(day.year, day.month, day.day, 12),
        review_date=day,
        grade=grade,
        quality=grade.quality,
        interval_before=interval_before,
        interval_after=1,
        ease_after=2.5,
    )


def test_compute_stats_numbers():
    cards = [Card(f"Q{i}", "A", "d.md", "D", i) for i in range(5)]
    ids = [c.id for c in cards]

    def st(i, due, interval, ease=2.5):
        return CardState(ids[i], Schedule(2, ease, interval), due=due, last_reviewed=days(-1))

    states = {
        ids[0]: st(0, days(-2), 3, ease=2.0),  # overdue
        ids[1]: st(1, days(0), 25, ease=2.6),  # due today, mature
        ids[2]: st(2, days(1), 6),
        ids[3]: st(3, days(3), 30, ease=2.4),  # mature
        # ids[4] is new
        "orphan": CardState("orphan", Schedule(1, 2.5, 1), days(0), days(-1)),
    }
    reviews = [
        log(days(-40), Grade.AGAIN, 5),  # outside the 30-day window
        log(days(-4), Grade.GOOD, 1),
        log(days(-2), Grade.AGAIN, 6),
        log(days(-1), Grade.EASY, 3),
        log(days(0), Grade.HARD, 1),
        log(days(0), Grade.AGAIN, 0),  # first view of a new card: not a recall attempt
    ]
    stats = compute_stats(cards, states, reviews, TODAY)

    assert (stats.total, stats.new, stats.learned, stats.mature) == (5, 1, 4, 2)
    assert stats.due_today == 2  # overdue + due today; the orphan is ignored
    assert stats.reviews_today == 2
    assert stats.retention == 0.75 and stats.retention_sample == 4
    assert stats.streak == 3  # today, yesterday, two days ago; day -3 was missed
    assert stats.average_ease == (2.0 + 2.6 + 2.5 + 2.4) / 4
    assert stats.forecast == [
        (days(0), 2), (days(1), 1), (days(2), 0), (days(3), 1),
        (days(4), 0), (days(5), 0), (days(6), 0),
    ]  # fmt: skip


def test_streak_is_kept_until_the_day_is_over():
    assert current_streak([days(-1), days(-2)], TODAY) == 2  # not reviewed yet today
    assert current_streak([days(-2), days(-3)], TODAY) == 0  # missed yesterday
    assert current_streak([], TODAY) == 0


def test_empty_deck_stats_render(console):
    stats = compute_stats([], {}, [], TODAY)
    assert stats.retention is None and stats.average_ease is None
    render_stats(stats, console)
    text = output(console)
    assert "Retention (last 30 days)" in text
    assert "Next 7 days" in text and "Today" in text
