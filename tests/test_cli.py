import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import output, scripted_keys
from memento import __version__
from memento.cli import main
from memento.deck import load_deck
from memento.store import Store


def run(argv, clock, console, keys=()):
    return main(argv, clock=clock, console=console, read_key=scripted_keys(*keys))


def test_init_creates_example_deck_and_never_overwrites(tmp_path, clock, console):
    deck = tmp_path / "cards"
    assert run(["init", str(deck)], clock, console) == 0
    assert (deck / "welcome.md").exists()
    assert (deck / ".memento.db").exists()
    assert len(load_deck(deck).cards) == 3

    (deck / "welcome.md").write_text("## Mine\nkeep me\n", encoding="utf-8")
    assert run(["init", str(deck)], clock, console) == 0
    assert (deck / "welcome.md").read_text(encoding="utf-8") == "## Mine\nkeep me\n"
    assert "nothing changed" in output(console)


def test_missing_deck_is_a_friendly_error(tmp_path, clock, console):
    code = run(["review", "--deck", str(tmp_path / "nope")], clock, console)
    assert code == 1
    assert "memento init" in output(console)


def test_deck_from_environment_variable(deck_dir, clock, console, monkeypatch):
    monkeypatch.setenv("MEMENTO_DECK", str(deck_dir))
    assert run(["list"], clock, console) == 0
    assert "4 card(s)" in output(console)


def test_add_then_list_with_deck_before_or_after_command(deck_dir, clock, console):
    code = run(
        ["--deck", str(deck_dir), "add", "sql", "-q", "What does JOIN do?", "-a", "Combines rows.",
         "-t", "sql, #db"],
        clock,
        console,
    )  # fmt: skip
    assert code == 0
    assert (deck_dir / "sql.md").read_text(encoding="utf-8") == (
        "# Sql\n\n## What does JOIN do?\ntags: sql, db\n\nCombines rows.\n"
    )
    assert run(["list", "--deck", str(deck_dir), "--file", "sql"], clock, console) == 0
    assert "What does JOIN do?" in output(console)
    assert "1 card(s)" in output(console)


def test_add_with_editor(deck_dir, clock, console, monkeypatch, tmp_path):
    fake_editor = tmp_path / "editor.py"
    fake_editor.write_text(
        textwrap.dedent(
            """
            import sys
            from pathlib import Path
            path = Path(sys.argv[1])
            text = path.read_text().replace("## \\n", "## Written in the editor?\\n")
            path.write_text(text + "Yes.\\n\\n## And a second card?\\n\\nAlso yes.\\n")
            """
        )
    )
    monkeypatch.setenv("EDITOR", f'"{sys.executable}" "{fake_editor}"')
    monkeypatch.delenv("VISUAL", raising=False)
    assert run(["add", "--deck", str(deck_dir), "inbox"], clock, console) == 0
    questions = [c.question for c in load_deck(deck_dir).cards if c.source == "inbox.md"]
    assert questions == ["Written in the editor?", "And a second card?"]


def test_review_over_several_days(deck_dir, clock, console):
    deck = ["--deck", str(deck_dir)]
    # Day 1: two new cards allowed, both graded Good -> due tomorrow.
    assert run(["review", *deck, "--new", "2"], clock, console, keys=" 3 3") == 0
    assert "Reviewed 2 of 2 cards" in output(console)

    # Same day: the daily new-card allowance is used up.
    assert run(["due", *deck, "--new", "2"], clock, console) == 0
    assert "Nothing to review right now." in output(console)
    assert "Next review due tomorrow" in output(console)
    assert "2 new card(s) are waiting" in output(console)

    # Day 2: yesterday's cards are due again, plus up to 2 new ones.
    clock.advance(days=1)
    assert run(["review", *deck, "--new", "0", "--limit", "1"], clock, console, keys=" 4") == 0
    with Store(deck_dir / ".memento.db") as store:
        intervals = sorted(s.schedule.interval for s in store.states().values())
    assert intervals == [1, 6]  # one card graduated to 6 days, the other still pending

    assert run(["stats", *deck], clock, console) == 0
    text = output(console)
    assert "Reviews today" in text
    assert re.search(r"Retention \(last 30 days\)\s+│\s+100% \(1 of 1\)", text)
    assert re.search(r"Streak\s+│\s+2 days", text)


def test_check_exit_codes_and_prune(deck_dir, clock, console):
    deck = ["--deck", str(deck_dir)]
    assert run(["check", *deck], clock, console) == 0
    assert "All good: 4 card(s) in 2 file(s)." in output(console)

    run(["review", *deck], clock, console, keys=" 3")  # creates saved state for one card
    (deck_dir / "git.md").write_text("## Broken\n", encoding="utf-8")
    assert run(["check", *deck], clock, console) == 1
    text = output(console)
    assert "git.md:1: error: card has no answer: 'Broken'" in text
    assert "1 saved card(s) no longer exist" in text

    assert run(["check", *deck, "--prune"], clock, console) == 1  # still has the error
    assert "Pruned saved progress for 1 removed card(s)." in output(console)


@pytest.mark.parametrize("args", [["--version"], ["review", "--limit", "-1"], []])
def test_argument_errors_and_version(args, capsys):
    with pytest.raises(SystemExit) as exc:
        main(args)
    if args == ["--version"]:
        assert exc.value.code == 0
        assert __version__ in capsys.readouterr().out
    else:
        assert exc.value.code == 2


def test_subprocess_smoke_review_with_piped_keys(deck_dir: Path):
    """Run the real entry point the way a user would, with keys piped on stdin."""
    env = {**os.environ, "MEMENTO_DECK": str(deck_dir), "COLUMNS": "100"}
    result = subprocess.run(
        [sys.executable, "-m", "memento", "review", "--new", "1"],
        input=" 3",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Reviewed 1 of 1 cards. Progress saved." in result.stdout

    listed = subprocess.run(
        [sys.executable, "-m", "memento", "list"],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )  # fmt: skip
    assert listed.returncode == 0
    assert "learned" in listed.stdout
