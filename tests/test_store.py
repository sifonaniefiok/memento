import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from memento.clock import today
from memento.deck import load_deck
from memento.scheduler import apply_grade
from memento.sm2 import Grade
from memento.store import SCHEMA_VERSION, Store, StoreError


def grade(store: Store, card, g: Grade, clock) -> None:
    previous = store.state(card.id)
    new = apply_grade(card.id, previous, g, today(clock))
    store.save_review(card, g, previous, new, clock.now())


def test_migrations_create_schema_once(tmp_path: Path):
    db = tmp_path / "m.db"
    with Store(db) as store:
        assert store.schema_version() == SCHEMA_VERSION
    with Store(db) as store:  # reopening must not re-run migration 1
        assert store.schema_version() == SCHEMA_VERSION
    rows = sqlite3.connect(db).execute("SELECT version FROM schema_migrations").fetchall()
    assert rows == [(1,)]


def test_database_from_newer_version_is_refused(tmp_path: Path):
    db = tmp_path / "m.db"
    Store(db).close()
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO schema_migrations VALUES (99, 'future')")
    conn.commit()
    conn.close()
    with pytest.raises(StoreError, match="schema version 99"):
        Store(db)


def test_state_and_history_persist_across_sessions(deck_dir: Path, clock):
    deck = load_deck(deck_dir)
    card = deck.cards[0]
    with Store(deck.db_path) as store:
        grade(store, card, Grade.GOOD, clock)

    clock.advance(days=1)
    with Store(deck.db_path) as store:  # a new process the next day
        state = store.state(card.id)
        assert state is not None and state.due == today(clock)
        grade(store, card, Grade.EASY, clock)

    with Store(deck.db_path) as store:
        state = store.states()[card.id]
        assert (state.schedule.repetitions, state.schedule.interval) == (2, 6)
        assert state.due == today(clock) + timedelta(days=6)
        history = store.reviews()
        assert [(r.grade, r.interval_before, r.interval_after) for r in history] == [
            (Grade.GOOD, 0, 1),
            (Grade.EASY, 1, 6),
        ]
        assert store.new_cards_seen_on(today(clock)) == 0
        assert store.new_cards_seen_on(today(clock) - timedelta(days=1)) == 1


def test_card_identity_survives_answer_edits_but_not_rewording(deck_dir: Path, clock):
    git = deck_dir / "git.md"
    deck = load_deck(deck_dir)
    card = next(c for c in deck.cards if c.question == "How do you stage part of a file?")
    with Store(deck.db_path) as store:
        grade(store, card, Grade.GOOD, clock)

    # Editing the answer, tags and capitalisation keeps the same id and history.
    git.write_text(
        git.read_text()
        .replace("git add -p", "Use `git add -p` and pick hunks.")
        .replace("tags: git", "tags: git, staging")
        .replace("stage part of a file", "STAGE part  of a file"),
        encoding="utf-8",
    )
    edited = load_deck(deck_dir)
    with Store(deck.db_path) as store:
        assert store.orphans(c.id for c in edited.cards) == []
        assert card.id in {c.id for c in edited.cards}

    # Rewording the question makes it a new card; the old row becomes an orphan.
    original = git.read_text()
    git.write_text(original.replace("STAGE part  of a file", "stage hunks"), encoding="utf-8")
    reworded = load_deck(deck_dir)
    with Store(deck.db_path) as store:
        assert card.id not in {c.id for c in reworded.cards}
        orphans = store.orphans(c.id for c in reworded.cards)
        assert [o.card_id for o in orphans] == [card.id]

    # Undoing the rewording brings the history back...
    git.write_text(original, encoding="utf-8")
    with Store(deck.db_path) as store:
        assert store.orphans(c.id for c in load_deck(deck_dir).cards) == []

        # ...and pruning removes orphans together with their review log.
        assert store.prune(c.id for c in reworded.cards) == 1
        assert store.state(card.id) is None
        assert store.reviews() == []


def test_moving_a_card_to_another_file_makes_it_new(deck_dir: Path, clock):
    deck = load_deck(deck_dir)
    card = deck.cards[0]
    with Store(deck.db_path) as store:
        grade(store, card, Grade.GOOD, clock)
    (deck_dir / "git.md").rename(deck_dir / "vcs.md")
    moved = load_deck(deck_dir)
    assert card.id not in {c.id for c in moved.cards}
