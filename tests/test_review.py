from datetime import timedelta

from conftest import output, scripted_keys
from memento.clock import today
from memento.deck import load_deck
from memento.review import describe_interval, run_session
from memento.sm2 import Grade
from memento.store import Store


def test_full_session_with_scripted_keys(deck_dir, clock, console):
    deck = load_deck(deck_dir)
    cards = deck.cards[:3]
    # Enter reveals, "3" grades Good; a stray "x" is ignored; Space also reveals.
    keys = scripted_keys("\r", "3", " ", "x", "4", "\n", "1")
    with Store(deck.db_path) as store:
        summary = run_session(cards, store, clock, console, keys)
        states = store.states()

    assert summary.reviewed == 3 and not summary.quit_early
    assert summary.grades == {Grade.GOOD: 1, Grade.EASY: 1, Grade.AGAIN: 1}
    assert set(states) == {c.id for c in cards}
    assert all(s.due == today(clock) + timedelta(days=1) for s in states.values())

    text = output(console)
    assert "Card 1 of 3" in text and "2 remaining" in text
    assert "How do you stage part of a file?" in text
    assert "git add -p" in text  # the answer was revealed
    assert "Good - next review tomorrow" in text
    assert "Reviewed 3 of 3 cards" in text


def test_answer_is_hidden_until_reveal(deck_dir, clock, console):
    deck = load_deck(deck_dir)
    with Store(deck.db_path) as store:
        run_session(deck.cards[:1], store, clock, console, scripted_keys("q"))
    text = output(console)
    assert "How do you stage part of a file?" in text
    assert "git add -p" not in text


def test_quitting_keeps_progress_already_made(deck_dir, clock, console):
    deck = load_deck(deck_dir)
    with Store(deck.db_path) as store:
        # Grade the first card, reveal the second, then quit at the grade prompt.
        summary = run_session(deck.cards, store, clock, console, scripted_keys(" ", "3", " ", "q"))
        assert summary.quit_early
        assert summary.reviewed == 1
        assert list(store.states()) == [deck.cards[0].id]
    assert "Reviewed 1 of 4 cards. Progress saved." in output(console)


def test_end_of_input_and_ctrl_c_end_the_session(deck_dir, clock, console):
    deck = load_deck(deck_dir)

    def interrupt() -> str:
        raise KeyboardInterrupt

    with Store(deck.db_path) as store:
        assert run_session(deck.cards, store, clock, console, scripted_keys()).quit_early
        assert run_session(deck.cards, store, clock, console, interrupt).quit_early
        assert store.states() == {}


def test_describe_interval_wording():
    assert describe_interval(1) == "tomorrow"
    assert describe_interval(6) == "in 6 days"
    assert describe_interval(90) == "in 3 months"
    assert describe_interval(1000) == "in 2.7 years"
