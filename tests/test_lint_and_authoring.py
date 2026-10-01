from pathlib import Path

import pytest

from memento.authoring import AddError, NewCard, append_cards, resolve_card_file
from memento.deck import load_deck
from memento.lint import check_deck


def test_check_reports_duplicates_empty_answers_and_unclosed_fences(tmp_path: Path):
    (tmp_path / "a.md").write_text(
        "## Q1\nA\n## Q1\nB\n## Empty\n\n## Code\n```\nunclosed\n", encoding="utf-8"
    )
    (tmp_path / "b.md").write_text("## q1\nsame question, other file\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("### not a card\n", encoding="utf-8")

    issues = [(i.source, i.line, i.severity) for i in check_deck(load_deck(tmp_path))]
    assert issues == [
        ("a.md", 3, "error"),  # duplicate question in the same file
        ("a.md", 5, "error"),  # empty answer
        ("a.md", 8, "warning"),  # unclosed code fence
        ("b.md", 1, "warning"),  # same question as a.md:1
        ("notes.md", 1, "warning"),  # no cards at all
    ]
    # Duplicates are reviewed once: the first one wins.
    assert [c.answer for c in load_deck(tmp_path).cards if c.question == "Q1"] == ["A"]


def test_check_is_clean_for_the_bundled_examples():
    examples = Path(__file__).parent.parent / "examples"
    deck = load_deck(examples)
    assert check_deck(deck) == []
    assert len(deck.cards) >= 10


def test_append_creates_file_with_title_and_round_trips(tmp_path: Path):
    path = resolve_card_file(tmp_path, "rust-basics")
    card = NewCard(
        "What is `cargo`?", "Rust's build tool.\n\n```sh\n## build\ncargo build\n```", ("rust",)
    )
    append_cards(path, tmp_path, [card])
    append_cards(path, tmp_path, [NewCard("What is `rustc`?", "The compiler.")])

    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Rust Basics\n\n## What is `cargo`?\ntags: rust\n")
    cards = load_deck(tmp_path).cards
    assert [c.question for c in cards] == ["What is `cargo`?", "What is `rustc`?"]
    assert cards[0].answer.endswith("cargo build\n```")


@pytest.mark.parametrize(
    ("card", "reason"),
    [
        (NewCard("Q", "line\n## sneaky heading"), "would not parse back"),
        (NewCard("Q", "before\n\n---\n\nafter"), "would not parse back"),
        (NewCard("Two\nlines", "A"), "single line"),
        (NewCard("Q", "   "), "empty"),
        (NewCard("Existing", "dup"), "already has"),
    ],
)
def test_append_refuses_cards_that_would_not_round_trip(tmp_path: Path, card, reason):
    path = tmp_path / "deck.md"
    original = "# Deck\n\n## Existing\nyes\n"
    path.write_text(original, encoding="utf-8")
    with pytest.raises(AddError, match=reason):
        append_cards(path, tmp_path, [card])
    assert path.read_text(encoding="utf-8") == original  # nothing written


def test_add_refuses_paths_outside_the_deck(tmp_path: Path):
    with pytest.raises(AddError, match="outside"):
        resolve_card_file(tmp_path, "../escape.md")
