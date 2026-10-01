from datetime import date, timedelta

from memento.parser import Card
from memento.scheduler import CardState, apply_grade, build_queue
from memento.sm2 import Grade, Schedule

TODAY = date(2026, 1, 5)


def make_cards(n: int) -> list[Card]:
    return [Card(f"Q{i}", f"A{i}", "deck.md", "Deck", i + 1) for i in range(n)]


def state(card: Card, due: date) -> CardState:
    return CardState(card.id, Schedule(1, 2.5, 1), due=due, last_reviewed=due - timedelta(days=1))


def test_apply_grade_sets_due_date_and_counts_lapses():
    first = apply_grade("id", None, Grade.GOOD, TODAY)
    assert first.due == TODAY + timedelta(days=1)
    assert first.lapses == 0
    second = apply_grade("id", first, Grade.GOOD, first.due)
    assert second.due == first.due + timedelta(days=6)
    forgotten = apply_grade("id", second, Grade.AGAIN, second.due)
    assert forgotten.lapses == 1
    assert forgotten.schedule.repetitions == 0
    assert forgotten.due == second.due + timedelta(days=1)


def test_queue_puts_most_overdue_first_then_new_cards():
    cards = make_cards(5)
    states = {
        cards[0].id: state(cards[0], TODAY),
        cards[1].id: state(cards[1], TODAY - timedelta(days=3)),
        cards[2].id: state(cards[2], TODAY + timedelta(days=1)),  # not due yet
    }
    queue = build_queue(cards, states, TODAY, limit=10, new_per_day=10)
    assert [c.question for c in queue] == ["Q1", "Q0", "Q3", "Q4"]


def test_new_cards_are_capped_per_day_including_earlier_sessions():
    cards = make_cards(10)
    assert len(build_queue(cards, {}, TODAY, limit=100, new_per_day=4)) == 4
    queue = build_queue(cards, {}, TODAY, limit=100, new_per_day=4, new_seen_today=3)
    assert [c.question for c in queue] == ["Q0"]
    assert build_queue(cards, {}, TODAY, limit=100, new_per_day=4, new_seen_today=9) == []


def test_limit_caps_the_whole_session_due_first():
    cards = make_cards(6)
    states = {c.id: state(c, TODAY) for c in cards[:4]}
    queue = build_queue(cards, states, TODAY, limit=3, new_per_day=10)
    assert [c.question for c in queue] == ["Q0", "Q1", "Q2"]
    assert build_queue(cards, states, TODAY, limit=0, new_per_day=10) == []
