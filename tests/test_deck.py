from pathlib import Path

from memento.deck import load_deck, markdown_files


def test_deck_includes_subfolders_and_skips_hidden_ones(tmp_path: Path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "topics" / "sql.md").write_text("## SELECT?\nReads rows.\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "notes.md").write_text("## Hidden?\nyes\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("# Alpha\n## A?\nyes\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("## Not markdown\nno\n", encoding="utf-8")

    assert [p.relative_to(tmp_path).as_posix() for p in markdown_files(tmp_path)] == [
        "a.md",
        "topics/sql.md",
    ]
    deck = load_deck(tmp_path)
    assert [(c.source, c.title) for c in deck.cards] == [
        ("a.md", "Alpha"),
        ("topics/sql.md", "sql"),
    ]
    assert [c.question for c in deck.filter("ALPHA")] == ["A?"]  # matches the title
    assert [c.question for c in deck.filter("topics/")] == ["SELECT?"]  # matches the path
