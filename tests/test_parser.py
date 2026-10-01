from memento.parser import card_id, normalize_question, parse_markdown


def parse(text: str):
    return parse_markdown(text, source="deck.md", default_title="deck")


def test_basic_cards_title_and_answers():
    parsed = parse("# Capitals\n\n## France?\n\nParis\n\n## Japan?\nTokyo\n")
    assert parsed.title == "Capitals"
    assert [(c.question, c.answer) for c in parsed.cards] == [
        ("France?", "Paris"),
        ("Japan?", "Tokyo"),
    ]
    assert all(c.title == "Capitals" for c in parsed.cards)
    assert [c.line for c in parsed.cards] == [3, 7]
    assert parsed.problems == []


def test_file_name_is_title_when_no_h1():
    parsed = parse("## Q\nA\n")
    assert parsed.title == "deck"
    assert parsed.cards[0].title == "deck"


def test_multiline_answer_keeps_inner_blank_lines_and_indentation():
    text = "## Q\n\nline one\n\n    indented code\n- item\n\n\n"
    card = parse(text).cards[0]
    assert card.answer == "line one\n\n    indented code\n- item"


def test_heading_inside_code_fence_does_not_start_a_card():
    text = "## Bash comment?\n\n```bash\n## not a question\n# nor a title\n---\n```\n\nDone.\n"
    parsed = parse(text)
    assert len(parsed.cards) == 1
    assert "## not a question" in parsed.cards[0].answer
    assert parsed.cards[0].answer.endswith("Done.")


def test_tilde_fences_and_longer_closing_fence():
    text = "## Q\n~~~~\n## inside\n~~~\n## still inside\n~~~~~\n## Next\nA\n"
    parsed = parse(text)
    assert [c.question for c in parsed.cards] == ["Q", "Next"]
    assert "## still inside" in parsed.cards[0].answer


def test_unclosed_fence_is_a_warning():
    parsed = parse("## Q\n```\ncode\n## swallowed\n")
    assert len(parsed.cards) == 1
    assert [(p.line, p.severity) for p in parsed.problems] == [(2, "warning")]


def test_thematic_break_ends_card_and_notes_after_it_are_ignored():
    parsed = parse("## Q\nAnswer\n\n---\nA private note\n\n## Q2\nA2\n")
    assert parsed.cards[0].answer == "Answer"
    assert parsed.cards[1].answer == "A2"


def test_crlf_and_bom_are_handled():
    parsed = parse("﻿# T\r\n\r\n## Q?\r\ntags: a\r\n\r\nAnswer\r\nmore\r\n")
    card = parsed.cards[0]
    assert parsed.title == "T"
    assert card.question == "Q?"
    assert card.tags == ("a",)
    assert card.answer == "Answer\nmore"
    assert "\r" not in card.answer


def test_empty_answer_and_empty_question_are_reported():
    parsed = parse("## Empty\n\n## \nbody\n## Fine\nyes\n")
    assert [c.question for c in parsed.cards] == ["Empty", "Fine"]
    assert parsed.cards[0].answer == ""
    messages = [(p.line, p.severity) for p in parsed.problems]
    assert messages == [(1, "error"), (3, "error")]


def test_tags_line_only_counts_as_first_body_line():
    parsed = parse("## Q\n\nTags: Git, #basics , \n\nAnswer\ntags: not tags\n")
    card = parsed.cards[0]
    assert card.tags == ("Git", "basics")
    assert card.answer == "Answer\ntags: not tags"


def test_unicode_questions_and_identity_normalisation():
    composed = "## Qu'est-ce que été ?\nsummer\n"
    decomposed = "## QU'EST-CE  QUE  été ?\nsummer\n"
    a, b = parse(composed).cards[0], parse(decomposed).cards[0]
    assert a.question == "Qu'est-ce que été ?"
    assert a.id == b.id  # case, spacing and Unicode form do not change identity
    assert normalize_question("  Hello\tWORLD ") == "hello world"


def test_card_id_depends_on_file_and_question():
    assert card_id("a.md", "Q") != card_id("b.md", "Q")
    assert card_id("a.md", "Q") != card_id("a.md", "Q2")
    assert len(card_id("a.md", "Q")) == 16


def test_front_matter_closing_hashes_and_deeper_headings():
    text = "---\ntitle: x\n# yaml comment\n---\n# Real Title\n## Q ##\n### Sub heading\nbody\n"
    parsed = parse(text)
    assert parsed.title == "Real Title"
    card = parsed.cards[0]
    assert card.question == "Q"
    assert card.answer == "### Sub heading\nbody"


def test_later_h1_ends_card_without_renaming_deck():
    parsed = parse("# One\n## Q\nA\n# Section two\nignored text\n## Q2\nA2\n")
    assert parsed.title == "One"
    assert [c.answer for c in parsed.cards] == ["A", "A2"]
    assert all(c.title == "One" for c in parsed.cards)
