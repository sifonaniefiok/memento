"""Command-line interface: ``memento init | review | add | list | due | stats | check``.

:func:`main` takes its clock, console and key reader as optional arguments.
The console script passes nothing (real terminal, real time); tests pass fakes
and call ``main([...])`` directly, which is why there is no global state here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from memento import __version__
from memento.authoring import (
    AddError,
    NewCard,
    append_cards,
    cards_from_editor,
    resolve_card_file,
)
from memento.clock import Clock, SystemClock, today
from memento.deck import DB_FILENAME, Deck, default_deck_dir, load_deck, markdown_files
from memento.lint import check_deck
from memento.parser import Card
from memento.review import KeyReader, describe_interval, read_terminal_key, run_session
from memento.scheduler import CardState, build_queue, is_due
from memento.stats import compute_stats, render_stats
from memento.store import Store, StoreError

DEFAULT_LIMIT = 100
DEFAULT_NEW_PER_DAY = 20

WELCOME_DECK = """\
# Welcome to Memento

Each `## heading` below is a question and the text under it is the answer.
This introduction is ignored because it comes before the first question.
Edit this file, or add your own `.md` files next to it.

## How do I start a review session?
tags: memento

Run `memento review`. Press **Enter** or **Space** to reveal the answer, then
grade yourself:

| Key | Grade | Meaning                         |
|-----|-------|---------------------------------|
| 1   | Again | I didn't remember it            |
| 2   | Hard  | I remembered, with difficulty   |
| 3   | Good  | I remembered after a moment     |
| 4   | Easy  | I knew it instantly             |

---

## Where is my review progress stored?
tags: memento

In `.memento.db`, a SQLite file in this folder. The Markdown is never modified
by reviewing, so you can edit, sync or version these files freely.

---

## Can an answer contain code?
tags: memento, markdown

Yes. Fenced code blocks are shown with syntax highlighting, and a `##` inside
a code block does not start a new card:

```python
## this is a comment, not a question
print("hello from Memento")
```
"""


@dataclass
class App:
    """Everything a command needs from the outside world."""

    console: Console
    err: Console
    clock: Clock
    read_key: KeyReader


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def build_parser() -> argparse.ArgumentParser:
    # --deck is accepted both before and after the sub-command. The sub-command
    # copy uses SUPPRESS so that, when omitted, it does not overwrite a value
    # given before the sub-command.
    deck_option = argparse.ArgumentParser(add_help=False)
    deck_option.add_argument(
        "--deck",
        type=Path,
        default=argparse.SUPPRESS,
        help="deck directory (default: $MEMENTO_DECK or ~/memento)",
    )

    parser = argparse.ArgumentParser(
        prog="memento",
        description="Spaced-repetition flashcards stored in plain Markdown.",
    )
    parser.add_argument("--version", action="version", version=f"memento {__version__}")
    parser.add_argument("--deck", type=Path, default=None, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    init = commands.add_parser("init", parents=[deck_option], help="create a deck directory")
    init.add_argument("path", nargs="?", type=Path, help="where to create it (default: deck)")

    def add_session_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--limit",
            type=_non_negative_int,
            default=DEFAULT_LIMIT,
            help=f"maximum cards in the session (default {DEFAULT_LIMIT})",
        )
        sub.add_argument(
            "--new",
            type=_non_negative_int,
            default=DEFAULT_NEW_PER_DAY,
            help=f"maximum new cards per day (default {DEFAULT_NEW_PER_DAY})",
        )
        sub.add_argument("--file", help="only cards whose file name or title contains this")

    review = commands.add_parser("review", parents=[deck_option], help="review due cards")
    add_session_options(review)

    due = commands.add_parser(
        "due", parents=[deck_option], help="list the cards a review would show now"
    )
    add_session_options(due)

    list_ = commands.add_parser("list", parents=[deck_option], help="list all cards")
    list_.add_argument("--file", help="only cards whose file name or title contains this")

    add = commands.add_parser(
        "add",
        parents=[deck_option],
        help="add a card (opens $EDITOR unless -q and -a are given)",
    )
    add.add_argument(
        "file", nargs="?", default="inbox.md", help="file in the deck (default inbox.md)"
    )
    add.add_argument("-q", "--question", help="the question (one line)")
    add.add_argument("-a", "--answer", help="the answer (Markdown)")
    add.add_argument("-t", "--tags", help="comma-separated tags")

    commands.add_parser("stats", parents=[deck_option], help="show statistics")

    check = commands.add_parser("check", parents=[deck_option], help="lint the Markdown files")
    check.add_argument(
        "--prune",
        action="store_true",
        help="delete saved progress for cards that no longer exist",
    )
    return parser


def _deck_dir(args: argparse.Namespace) -> Path:
    return (args.deck or default_deck_dir()).expanduser()


def _load(app: App, args: argparse.Namespace) -> Deck | None:
    """Load the deck, or explain how to create one."""
    directory = _deck_dir(args)
    if not directory.is_dir():
        app.err.print(
            f"[red]No deck directory at {escape(str(directory))}.[/] Run [bold]memento init[/] "
            "or pass --deck PATH.",
            soft_wrap=True,
        )
        return None
    return load_deck(directory)


# -- commands -------------------------------------------------------------------


def cmd_init(app: App, args: argparse.Namespace) -> int:
    directory = (args.path or _deck_dir(args)).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    say = app.console.print
    existing = markdown_files(directory)
    if existing:
        say(
            escape(f"{directory} already has {len(existing)} Markdown file(s); nothing changed."),
            soft_wrap=True,
        )
    else:
        (directory / "welcome.md").write_text(WELCOME_DECK, encoding="utf-8")
        say(escape(f"Created {directory / 'welcome.md'}"), soft_wrap=True)
    Store(directory / DB_FILENAME).close()

    next_step = "memento review"
    if directory.resolve() != default_deck_dir().expanduser().resolve():
        next_step += f" --deck {directory}"
    say(f"Deck ready. Next: [bold]{escape(next_step)}[/]", soft_wrap=True)
    return 0


def _queue(
    app: App, args: argparse.Namespace, deck: Deck, store: Store
) -> tuple[list[Card], list[Card], dict[str, CardState], date]:
    """Build today's review queue, honouring --limit, --new and --file."""
    day = today(app.clock)
    states = store.states()
    cards = deck.filter(args.file)
    queue = build_queue(
        cards,
        states,
        day,
        limit=args.limit,
        new_per_day=args.new,
        new_seen_today=store.new_cards_seen_on(day),
    )
    return queue, cards, states, day


def _nothing_due_message(
    app: App, cards: list[Card], states: dict[str, CardState], day: date, new_limit: int
) -> None:
    app.console.print("[green]Nothing to review right now.[/]")
    upcoming = sorted(
        states[c.id].due for c in cards if c.id in states and not is_due(states[c.id], day)
    )
    if upcoming:
        days = (upcoming[0] - day).days
        app.console.print(f"Next review due {describe_interval(days)} ({upcoming[0]}).")
    waiting = sum(1 for c in cards if c.id not in states)
    if waiting:
        app.console.print(
            f"{waiting} new card(s) are waiting; today's limit of {new_limit} new cards "
            "is reached (raise it with --new N)."
        )
    elif not cards:
        app.console.print("The deck has no cards yet. Add one with [bold]memento add[/].")


def cmd_review(app: App, args: argparse.Namespace) -> int:
    deck = _load(app, args)
    if deck is None:
        return 1
    with Store(deck.db_path) as store:
        queue, cards, states, day = _queue(app, args, deck, store)
        if not queue:
            _nothing_due_message(app, cards, states, day, args.new)
            return 0
        new = sum(1 for c in queue if c.id not in states)
        app.console.print(
            f"[bold]{len(queue)}[/] card(s) to review: {len(queue) - new} due, {new} new."
        )
        run_session(queue, store, app.clock, app.console, app.read_key)
    return 0


def _status(card_id: str, states: dict[str, CardState], day: date) -> tuple[str, str, str]:
    """(status, due date, interval) columns for the list tables."""
    state = states.get(card_id)
    if state is None:
        return "[cyan]new[/]", "-", "-"
    status = "[yellow]due[/]" if is_due(state, day) else "learned"
    return status, state.due.isoformat(), f"{state.schedule.interval}d"


def _cards_table(title: str, cards: list[Card], states: dict[str, CardState], day: date) -> Table:
    table = Table(title=title, title_justify="left")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("File", no_wrap=True)
    table.add_column("Question")
    table.add_column("Status", no_wrap=True)
    table.add_column("Due", no_wrap=True)
    table.add_column("Ivl", justify="right", no_wrap=True)
    for card in cards:
        status, due, interval = _status(card.id, states, day)
        table.add_row(
            card.id[:8],
            escape(f"{card.source}:{card.line}"),
            escape(card.question),
            status,
            due,
            interval,
        )
    return table


def cmd_list(app: App, args: argparse.Namespace) -> int:
    deck = _load(app, args)
    if deck is None:
        return 1
    with Store(deck.db_path) as store:
        states = store.states()
    cards = deck.filter(args.file)
    if not cards:
        app.console.print("No cards found.")
        return 0
    app.console.print(_cards_table(f"{len(cards)} card(s)", cards, states, today(app.clock)))
    return 0


def cmd_due(app: App, args: argparse.Namespace) -> int:
    deck = _load(app, args)
    if deck is None:
        return 1
    with Store(deck.db_path) as store:
        queue, cards, states, day = _queue(app, args, deck, store)
    if not queue:
        _nothing_due_message(app, cards, states, day, args.new)
        return 0
    app.console.print(_cards_table(f"{len(queue)} card(s) to review now", queue, states, day))
    return 0


def _split_tags(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(t.strip().lstrip("#") for t in raw.split(",") if t.strip().lstrip("#"))


def cmd_add(app: App, args: argparse.Namespace) -> int:
    directory = _deck_dir(args)
    if not directory.is_dir():
        app.err.print(
            f"[red]No deck directory at {escape(str(directory))}.[/] Run [bold]memento init[/]."
        )
        return 1
    try:
        path = resolve_card_file(directory, args.file)
        if args.question and args.answer:
            cards = [NewCard(args.question, args.answer, _split_tags(args.tags))]
        else:
            cards = cards_from_editor(args.question or "", args.answer or "")
            if not cards:
                app.console.print("No question written; nothing added.")
                return 0
        append_cards(path, directory, cards)
    except AddError as exc:
        app.err.print(f"[red]Not added:[/] {escape(str(exc))}")
        return 1
    for card in cards:
        where = path.relative_to(directory.resolve()).as_posix()
        app.console.print(escape(f"Added to {where}: {card.question}"))
    return 0


def cmd_stats(app: App, args: argparse.Namespace) -> int:
    deck = _load(app, args)
    if deck is None:
        return 1
    with Store(deck.db_path) as store:
        stats = compute_stats(deck.cards, store.states(), store.reviews(), today(app.clock))
    render_stats(stats, app.console)
    return 0


def cmd_check(app: App, args: argparse.Namespace) -> int:
    deck = _load(app, args)
    if deck is None:
        return 1
    issues = check_deck(deck)
    for issue in issues:
        style = "red" if issue.severity == "error" else "yellow"
        app.console.print(
            f"{escape(issue.source)}:{issue.line}: [{style}]{issue.severity}[/]: "
            f"{escape(issue.message)}"
        )

    if deck.db_path.exists():
        known = {card.id for card in deck.all_cards}
        with Store(deck.db_path) as store:
            if args.prune:
                removed = store.prune(known)
                app.console.print(f"Pruned saved progress for {removed} removed card(s).")
            else:
                orphans = store.orphans(known)
                if orphans:
                    app.console.print(
                        f"{len(orphans)} saved card(s) no longer exist in the Markdown "
                        "(deleted, renamed or reworded). They are ignored; run "
                        "[bold]memento check --prune[/] to delete their progress."
                    )

    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = len(issues) - errors
    files = len(deck.files)
    cards = len(deck.cards)
    if issues:
        app.console.print(
            f"{cards} card(s) in {files} file(s): {errors} error(s), {warnings} warning(s)."
        )
    else:
        app.console.print(f"[green]All good:[/] {cards} card(s) in {files} file(s).")
    return 1 if errors else 0


COMMANDS = {
    "init": cmd_init,
    "review": cmd_review,
    "due": cmd_due,
    "list": cmd_list,
    "add": cmd_add,
    "stats": cmd_stats,
    "check": cmd_check,
}


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Clock | None = None,
    console: Console | None = None,
    read_key: KeyReader | None = None,
) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    app = App(
        console=console or Console(highlight=False),
        err=console or Console(stderr=True, highlight=False),
        clock=clock or SystemClock(),
        read_key=read_key or read_terminal_key,
    )
    try:
        return COMMANDS[args.command](app, args)
    except StoreError as exc:
        app.err.print(f"[red]{escape(str(exc))}[/]")
        return 1
    except KeyboardInterrupt:
        app.err.print("Interrupted.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
