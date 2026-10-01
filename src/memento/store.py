"""SQLite persistence for scheduling state and review history.

Why a database at all when the cards are Markdown? Because review state
changes every day and is noisy (ease factors, intervals, timestamps). Writing
it into the Markdown would turn every review into a diff in your notes. So the
Markdown says *what* to learn, and ``.memento.db`` (inside the deck directory)
remembers *when*. Delete the database and you lose your progress, never your
cards.

Two tables matter:

* ``cards`` - one row per card that has been reviewed at least once, keyed by
  the card id (a hash of file + question, see :func:`memento.parser.card_id`).
* ``reviews`` - an append-only log of every answer, used for statistics.

The schema is versioned with a ``schema_migrations`` table so future versions
can change it without breaking existing review history.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from memento import sm2
from memento.parser import Card
from memento.scheduler import CardState

# Each migration runs once, in order, inside a transaction. Never edit a
# migration that has been released: add a new one instead.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE cards (
            id            TEXT PRIMARY KEY,
            source        TEXT NOT NULL,
            question      TEXT NOT NULL,
            repetitions   INTEGER NOT NULL,
            ease          REAL NOT NULL,
            interval      INTEGER NOT NULL,
            due           TEXT NOT NULL,
            last_reviewed TEXT NOT NULL,
            lapses        INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id         TEXT NOT NULL,
            reviewed_at     TEXT NOT NULL,
            review_date     TEXT NOT NULL,
            grade           INTEGER NOT NULL,
            quality         INTEGER NOT NULL,
            interval_before INTEGER NOT NULL,
            interval_after  INTEGER NOT NULL,
            ease_after      REAL NOT NULL
        );
        CREATE INDEX reviews_by_card ON reviews (card_id);
        CREATE INDEX reviews_by_date ON reviews (review_date);
        """,
    ),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]


class StoreError(Exception):
    """The database cannot be used (e.g. it was written by a newer Memento)."""


@dataclass(frozen=True)
class ReviewLog:
    """One row of the review history."""

    card_id: str
    reviewed_at: datetime
    review_date: date
    grade: sm2.Grade
    quality: int
    interval_before: int
    interval_after: int
    ease_after: float


@dataclass(frozen=True)
class OrphanRow:
    """Scheduling state for a card that no longer exists in any Markdown file."""

    card_id: str
    source: str
    question: str


class Store:
    """A small repository around one SQLite file. Use as a context manager."""

    def __init__(self, path: Path | str) -> None:
        self.path = path
        # isolation_level=None: we issue BEGIN/COMMIT ourselves so it is obvious
        # where each transaction starts and ends.
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- schema ---------------------------------------------------------------

    def _migrate(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        current = self.schema_version()
        if current > SCHEMA_VERSION:
            raise StoreError(
                f"{self.path} uses schema version {current}, but this Memento only "
                f"understands up to {SCHEMA_VERSION}. Please upgrade Memento."
            )
        for version, sql in MIGRATIONS:
            if version <= current:
                continue
            applied_at = datetime.now().astimezone().isoformat(timespec="seconds")
            # executescript() runs the whole migration plus its bookkeeping row
            # as one transaction: either all of it applies or none of it does.
            self._conn.executescript(
                f"BEGIN;\n{sql}\n"
                f"INSERT INTO schema_migrations (version, applied_at) "
                f"VALUES ({int(version)}, '{applied_at}');\nCOMMIT;"
            )

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return row[0] or 0

    # -- card state -----------------------------------------------------------

    @staticmethod
    def _row_to_state(row: sqlite3.Row) -> CardState:
        return CardState(
            card_id=row["id"],
            schedule=sm2.Schedule(
                repetitions=row["repetitions"], ease=row["ease"], interval=row["interval"]
            ),
            due=date.fromisoformat(row["due"]),
            last_reviewed=date.fromisoformat(row["last_reviewed"]),
            lapses=row["lapses"],
        )

    def states(self) -> dict[str, CardState]:
        """State of every card ever reviewed, keyed by card id."""
        rows = self._conn.execute("SELECT * FROM cards").fetchall()
        return {row["id"]: self._row_to_state(row) for row in rows}

    def state(self, card_id: str) -> CardState | None:
        row = self._conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return self._row_to_state(row) if row else None

    def save_review(
        self,
        card: Card,
        grade: sm2.Grade,
        previous: CardState | None,
        new_state: CardState,
        reviewed_at: datetime,
    ) -> None:
        """Persist one answer: update the card's state and append to the history.

        Both writes happen in a single transaction, and each review is committed
        straight away, so quitting halfway through a session loses nothing.
        """
        interval_before = previous.schedule.interval if previous else 0
        schedule = new_state.schedule
        with self._transaction():
            self._conn.execute(
                """
                INSERT INTO cards (id, source, question, repetitions, ease, interval,
                                   due, last_reviewed, lapses)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    source = excluded.source, question = excluded.question,
                    repetitions = excluded.repetitions, ease = excluded.ease,
                    interval = excluded.interval, due = excluded.due,
                    last_reviewed = excluded.last_reviewed, lapses = excluded.lapses
                """,
                (
                    card.id,
                    card.source,
                    card.question,
                    schedule.repetitions,
                    schedule.ease,
                    schedule.interval,
                    new_state.due.isoformat(),
                    new_state.last_reviewed.isoformat(),
                    new_state.lapses,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO reviews (card_id, reviewed_at, review_date, grade, quality,
                                     interval_before, interval_after, ease_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    reviewed_at.isoformat(timespec="seconds"),
                    reviewed_at.date().isoformat(),
                    int(grade),
                    grade.quality,
                    interval_before,
                    schedule.interval,
                    schedule.ease,
                ),
            )

    def _transaction(self) -> _Transaction:
        return _Transaction(self._conn)

    # -- history --------------------------------------------------------------

    def reviews(self) -> list[ReviewLog]:
        """The full review history, oldest first."""
        rows = self._conn.execute("SELECT * FROM reviews ORDER BY id").fetchall()
        return [
            ReviewLog(
                card_id=row["card_id"],
                reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
                review_date=date.fromisoformat(row["review_date"]),
                grade=sm2.Grade(row["grade"]),
                quality=row["quality"],
                interval_before=row["interval_before"],
                interval_after=row["interval_after"],
                ease_after=row["ease_after"],
            )
            for row in rows
        ]

    def new_cards_seen_on(self, day: date) -> int:
        """How many cards had their very first review on ``day``.

        Used to enforce the new-cards-per-day limit across several sessions.
        """
        row = self._conn.execute(
            "SELECT COUNT(*) FROM (SELECT MIN(review_date) AS first FROM reviews "
            "GROUP BY card_id) WHERE first = ?",
            (day.isoformat(),),
        ).fetchone()
        return int(row[0])

    # -- housekeeping ---------------------------------------------------------

    def orphans(self, known_ids: Iterable[str]) -> list[OrphanRow]:
        """Rows for cards that are no longer in any Markdown file.

        This happens when a card is deleted, its question reworded, or its file
        renamed. Orphans are simply ignored by review and stats; if the question
        is restored, the card picks up its old history again.
        """
        known = set(known_ids)
        rows = self._conn.execute("SELECT id, source, question FROM cards ORDER BY source")
        return [
            OrphanRow(row["id"], row["source"], row["question"])
            for row in rows
            if row["id"] not in known
        ]

    def prune(self, known_ids: Iterable[str]) -> int:
        """Delete orphaned card rows and their history. Returns how many cards."""
        orphan_ids = [(row.card_id,) for row in self.orphans(known_ids)]
        with self._transaction():
            self._conn.executemany("DELETE FROM reviews WHERE card_id = ?", orphan_ids)
            self._conn.executemany("DELETE FROM cards WHERE id = ?", orphan_ids)
        return len(orphan_ids)


class _Transaction:
    """``with`` block that commits on success and rolls back on any exception."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> None:
        self._conn.execute("BEGIN")

    def __exit__(self, exc_type: object, *rest: object) -> None:
        self._conn.execute("ROLLBACK" if exc_type else "COMMIT")
