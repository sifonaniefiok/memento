"""The interactive review session.

The session never reads the keyboard or prints to the screen directly: it is
handed a ``read_key`` function and a rich ``Console``. In the real app those
are the terminal; in tests they are a list of scripted key presses and an
in-memory console. That is what makes a whole session testable end to end.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from memento.clock import Clock, today
from memento.parser import Card
from memento.scheduler import CardState, apply_grade
from memento.sm2 import Grade
from memento.store import Store

KeyReader = Callable[[], str]
"""Returns one key press as a string. An empty string means input has ended."""

REVEAL_KEYS = frozenset({"\r", "\n", " "})
QUIT_KEYS = frozenset({"q", "Q", "\x03", "\x04", ""})  # q, Ctrl-C, Ctrl-D, end of input
GRADE_KEYS = {"1": Grade.AGAIN, "2": Grade.HARD, "3": Grade.GOOD, "4": Grade.EASY}
_GRADE_STYLE = {Grade.AGAIN: "red", Grade.HARD: "yellow", Grade.GOOD: "green", Grade.EASY: "cyan"}


@dataclass
class SessionSummary:
    """What happened in a session, for the closing message and for tests."""

    planned: int
    reviewed: int = 0
    grades: Counter[Grade] = field(default_factory=Counter)
    quit_early: bool = False


def describe_interval(days: int) -> str:
    """Human wording for an interval: 'tomorrow', 'in 6 days', 'in 3 months'."""
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days < 60:
        return f"in {days} days"
    if days < 730:
        return f"in {round(days / 30)} months"
    return f"in {days / 365:.1f} years"


def _wait_for(read_key: KeyReader, accepted: frozenset[str] | set[str]) -> str:
    """Read keys until one of ``accepted`` arrives; anything else is ignored."""
    while True:
        try:
            key = read_key()
        except (KeyboardInterrupt, EOFError):
            return ""
        if key in accepted or key in QUIT_KEYS:
            return key


def _grade_bar(card_id: str, previous: CardState | None, day: date) -> Text:
    """The grade prompt, previewing the interval each answer would give."""
    bar = Text()
    for key, grade in GRADE_KEYS.items():
        days = apply_grade(card_id, previous, grade, day).schedule.interval
        bar.append(f" {key} ", style=f"bold reverse {_GRADE_STYLE[grade]}")
        bar.append(f" {grade.label} ", style=f"bold {_GRADE_STYLE[grade]}")
        bar.append(f"({days}d)   ", style="dim")
    bar.append("q quit", style="dim")
    return bar


def run_session(
    cards: Sequence[Card],
    store: Store,
    clock: Clock,
    console: Console,
    read_key: KeyReader,
) -> SessionSummary:
    """Show each card, reveal the answer on Enter/Space, grade it with 1-4.

    Every grade is saved immediately, so pressing ``q`` (or Ctrl-C) at any
    point keeps the progress made so far.
    """
    summary = SessionSummary(planned=len(cards))
    for position, card in enumerate(cards, start=1):
        remaining = len(cards) - position
        console.rule(f"[bold]Card {position} of {len(cards)}[/]  [dim]{remaining} remaining[/]")
        header = Text(f"{card.title}  ·  {card.source}:{card.line}", style="dim")
        if card.tags:
            header.append("  #" + " #".join(card.tags), style="magenta")
        console.print(header)
        console.print(Panel(Markdown(card.question), title="Question", border_style="blue"))
        console.print(Text("Enter/Space show answer · q quit", style="dim"))

        if _wait_for(read_key, REVEAL_KEYS) in QUIT_KEYS:
            summary.quit_early = True
            break

        answer = Markdown(card.answer) if card.answer else Text("(no answer)", style="italic")
        console.print(Panel(answer, title="Answer", border_style="green"))

        day = today(clock)
        previous = store.state(card.id)
        console.print(_grade_bar(card.id, previous, day))
        key = _wait_for(read_key, frozenset(GRADE_KEYS))
        if key in QUIT_KEYS:
            summary.quit_early = True
            break

        grade = GRADE_KEYS[key]
        new_state = apply_grade(card.id, previous, grade, day)
        store.save_review(card, grade, previous, new_state, clock.now())
        summary.reviewed += 1
        summary.grades[grade] += 1
        console.print(
            Text.assemble(
                (grade.label, f"bold {_GRADE_STYLE[grade]}"),
                f" - next review {describe_interval(new_state.schedule.interval)} "
                f"({new_state.due.isoformat()})",
            )
        )
        console.print()

    _print_summary(summary, console)
    return summary


def _print_summary(summary: SessionSummary, console: Console) -> None:
    console.rule("[bold]Session complete" if not summary.quit_early else "[bold]Session ended")
    console.print(f"Reviewed {summary.reviewed} of {summary.planned} cards. Progress saved.")
    if summary.reviewed:
        parts = [
            f"{grade.label}: {summary.grades[grade]}" for grade in Grade if summary.grades[grade]
        ]
        console.print("  ".join(parts))


def read_terminal_key() -> str:
    """Read a single key press from the real terminal without waiting for Enter.

    When stdin is not a terminal (piped input, CI), characters are read one
    at a time instead, so ``printf ' 3 3' | memento review`` works too.
    """
    if not sys.stdin.isatty():
        return sys.stdin.read(1)
    if os.name == "nt":  # pragma: no cover - Windows is not in CI
        import msvcrt

        return msvcrt.getwch()

    import termios
    import tty

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        # cbreak: keys arrive immediately, but Ctrl-C still raises KeyboardInterrupt.
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
