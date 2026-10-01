# Memento

[![CI](https://github.com/sifonaniefiok/memento/actions/workflows/ci.yml/badge.svg)](https://github.com/sifonaniefiok/memento/actions/workflows/ci.yml)

A spaced-repetition flashcard app for terminal users. Cards are stored in plain
Markdown files so they're readable without the app.

```
╭────────────────────────────────── Question ──────────────────────────────────╮
│ How do you stage only some of the changes in a file?                         │
╰──────────────────────────────────────────────────────────────────────────────╯
Enter/Space show answer · q quit
```

- **Your cards are just Markdown.** A `## heading` is a question, the text under
  it is the answer. Read them on GitHub, edit them in any editor, grep them,
  version them with git.
- **Scheduling is SM-2**, the algorithm behind SuperMemo and early Anki: cards
  you know well come back rarely, cards you struggle with come back soon.
- **Progress lives in SQLite**, in a `.memento.db` file next to your cards. The
  Markdown is never rewritten by reviewing.
- **Built for the terminal**: one-key reviews, syntax-highlighted code in
  answers, stats tables, and a linter for your card files.

## Why plain Markdown?

Most flashcard apps keep your cards in a database or a proprietary format.
If the app goes away, or you just want to read your notes on your phone, you
are stuck with an export. Memento splits the problem in two:

| What                         | Where                     | Why                                   |
|------------------------------|---------------------------|---------------------------------------|
| The cards (questions/answers)| `*.md` files you own      | Human-readable, diffable, portable    |
| When to show each card       | `.memento.db` (SQLite)    | Changes daily; would be noise in Markdown |

Deleting the database loses your review history, never your cards.

## The card file format

````markdown
# Git

Anything before the first question is an introduction and is ignored.

## How do you stage only some of the changes in a file?
tags: git, staging

```bash
git add -p path/to/file
```

Git walks through each change ("hunk") and asks whether to stage it.

---

## What does `git stash` do?

It saves your uncommitted changes on a stack.
````

This file is one deck titled "Git" (without the `# Git` line it would be
titled after the file name) with two cards. The first card has two tags and an
answer that includes a code block; the `---` line ends it explicitly.

The rules:

| Markdown                         | Meaning                                                        |
|----------------------------------|----------------------------------------------------------------|
| `# Title`                        | Deck title, if it comes before the first card. Later `#` headings just end the current card. |
| `## Question`                    | Starts a card. The question is the heading text (one line).    |
| `tags: a, b`                     | Optional comma-separated tags, only as the first line of the answer. |
| everything else                  | The answer: any Markdown, multiple paragraphs, lists, tables, code. |
| `---` (or `***`, `___`)          | Ends the current card. Text after it, before the next `##`, is a private note. |
| ```` ``` ```` / `~~~` fenced code | Never structural: a `## comment` inside a code block does not start a card. |
| `###` and deeper headings        | Part of the answer.                                            |

Also handled: Windows line endings (CRLF), a UTF-8 byte-order mark, YAML front
matter at the top of a file, and closing hashes (`## Question ##`).

Tip: leave a blank line before `---`. In CommonMark a `---` directly under a
line of text turns that text into a heading on GitHub (Memento itself does not
care).

See [`examples/`](examples/) for two small decks on Git and Python.

## Install

Memento needs Python 3.10+ and is not published on PyPI; install it from GitHub:

```bash
pipx install git+https://github.com/sifonaniefiok/memento
# or
pip install git+https://github.com/sifonaniefiok/memento
```

Its only runtime dependency is [rich](https://github.com/Textualize/rich).

## Usage

Every command works on a *deck directory*: `--deck PATH` if given (before or
after the command), else `$MEMENTO_DECK`, else `~/memento`. Every `.md` file in
it (including sub-folders, skipping hidden ones like `.git`) is a deck.

### `memento init [PATH]`

Creates the deck directory with a `welcome.md` example and an empty database.
It never overwrites existing Markdown files.

```
$ memento init
Created /home/you/memento/welcome.md
Deck ready. Next: memento review
```

### `memento add [FILE] [-q QUESTION -a ANSWER] [-t TAGS]`

Appends a card to `FILE` in the deck (default `inbox.md`; `.md` is added for
you, and a new file gets a `# Title` from its name). With both `-q` and `-a` it
writes directly; otherwise it opens `$VISUAL` or `$EDITOR`
on a template where you can write one or more cards (`vi` is used if neither
is set, `notepad` on Windows).

```
$ memento add git -q "How do you rename the current branch?" -a 'Run `git branch -m new-name`.' -t "git, branches"
Added to git.md: How do you rename the current branch?
```

which appends exactly this to `git.md`:

```markdown
## How do you rename the current branch?
tags: git, branches

Run `git branch -m new-name`.
```

Every append is verified by re-parsing the file. If an answer contains
something that would split the card (a `## ` line or `---` outside a code
block), or the question already exists in that file, nothing is written and
`add` explains why.

### `memento review [--limit N] [--new N] [--file NAME]`

Runs a review session: due cards first (most overdue first), then new cards.

| Key             | Action                      |
|-----------------|-----------------------------|
| Enter / Space   | Reveal the answer           |
| `1`             | Again: I didn't remember it |
| `2`             | Hard: remembered with difficulty |
| `3`             | Good: remembered after a moment |
| `4`             | Easy: knew it instantly     |
| `q` / Ctrl-C    | Quit (progress is kept)     |

- `--limit N` caps the whole session (default 100).
- `--new N` caps new cards **per day** (default 20), counted across sessions,
  so running `review` twice does not double your new cards.
- `--file NAME` only reviews cards whose file name or deck title contains NAME.

Each grade is saved the moment you press it. The grade bar shows the interval
each answer would give. Real output (keys piped in with
`printf ' 3 4 1 3' | memento review --new 4`, which also works for scripting):

```
4 card(s) to review: 0 due, 4 new.
─────────────────────────── Card 1 of 4  3 remaining ───────────────────────────
Git  ·  git.md:6  #git #staging
╭────────────────────────────────── Question ──────────────────────────────────╮
│ How do you stage only some of the changes in a file?                         │
╰──────────────────────────────────────────────────────────────────────────────╯
Enter/Space show answer · q quit
╭─────────────────────────────────── Answer ───────────────────────────────────╮
│                                                                              │
│  git add -p path/to/file                                                     │
│                                                                              │
│                                                                              │
│ Git walks through each change ("hunk") and asks whether to stage it: y yes,  │
│ n no, s split into smaller hunks, q quit.                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
 1  Again (1d)    2  Hard (1d)    3  Good (1d)    4  Easy (1d)   q quit
Good - next review tomorrow (2026-10-02)

   ... three more cards ...

─────────────────────────────── Session complete ───────────────────────────────
Reviewed 4 of 4 cards. Progress saved.
Again: 1  Good: 2  Easy: 1
```

(In a terminal the grade keys and panels are coloured; new cards always start
at 1 day, see [How scheduling works](#how-scheduling-works).)

### `memento list [--file NAME]` and `memento due [--limit N] [--new N] [--file NAME]`

`list` shows every card with its status; `due` previews exactly the cards a
`review` with the same options would show right now.

```
$ memento list --file python
5 card(s)
┏━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━┳━━━━━┓
┃ ID       ┃ File         ┃ Question                      ┃ Status ┃ Due ┃ Ivl ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━╇━━━━━┩
│ b869af5b │ python.md:3  │ What does `if __name__ ==     │ new    │ -   │   - │
│          │              │ "__main__":` do?              │        │     │     │
│ 5a3bf40e │ python.md:11 │ Why is `def f(items=[])` a    │ new    │ -   │   - │
│          │              │ bug?                          │        │     │     │
│ 356465f3 │ python.md:27 │ What is the difference        │ new    │ -   │   - │
│          │              │ between `is` and `==`?        │        │     │     │
│ 0cd7b991 │ python.md:35 │ How do you swap two variables │ new    │ -   │   - │
│          │              │ in Python?                    │        │     │     │
│ f7d85454 │ python.md:47 │ What does a list              │ new    │ -   │   - │
│          │              │ comprehension with a          │        │     │     │
│          │              │ condition look like?          │        │     │     │
└──────────┴──────────────┴───────────────────────────────┴────────┴─────┴─────┘
```

When nothing is due, both `due` and `review` say when the next card is:

```
$ memento due --new 0
Nothing to review right now.
Next review due tomorrow (2026-10-02).
10 new card(s) are waiting; today's limit of 0 new cards is reached (raise it
with --new N).
```

### `memento stats`

```
$ memento stats
Memento stats
┌─────────────────────────────────────┬───────┐
│ Cards                               │    14 │
│ New (never reviewed)                │    10 │
│ Learned                             │     4 │
│   of which mature (interval >= 21d) │     0 │
│ Due today                           │     0 │
│ Reviews today                       │     4 │
│ Retention (last 30 days)            │     - │
│ Streak                              │ 1 day │
│ Average ease                        │  2.39 │
└─────────────────────────────────────┴───────┘
Next 7 days
┏━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Day        ┃ Due ┃                      ┃
┡━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Today      │   0 │                      │
│ Fri 02 Oct │   4 │ ████████████████████ │
│ Sat 03 Oct │   0 │                      │
│ Sun 04 Oct │   0 │                      │
│ Mon 05 Oct │   0 │                      │
│ Tue 06 Oct │   0 │                      │
│ Wed 07 Oct │   0 │                      │
└────────────┴─────┴──────────────────────┘
```

- **Learned** = reviewed at least once; **mature** = interval of 21+ days.
- **Due today** includes overdue cards; new cards are counted separately.
- **Retention** is the share of *recall attempts* (reviews of cards you had
  already learned) graded Hard, Good or Easy in the last 30 days. First views of
  new cards are excluded, which is why it shows `-` on day one.
- **Streak** counts consecutive days with at least one review. It is not broken
  until a whole day passes without reviewing.

### `memento check [--prune]`

Lints every Markdown file and exits with status 1 if there are errors, so it
can run in a pre-commit hook or CI.

```
$ memento check
scratch.md:1: error: card has no answer: 'Broken card'
scratch.md:5: error: duplicate question 'two' (first on line 3)
16 card(s) in 4 file(s): 2 error(s), 0 warning(s).
```

| Check                                  | Severity |
|----------------------------------------|----------|
| Same question twice in one file        | error (both would share one schedule; only the first is reviewed) |
| Card with an empty answer              | error    |
| `##` heading with no question text     | error    |
| Code fence that is never closed        | warning  |
| Same question in two different files   | warning  |
| Markdown file with no cards            | warning  |

It also reports saved progress for cards that no longer exist;
`--prune` deletes those rows and their review history.

## How scheduling works

Memento uses **SM-2** (Piotr Wozniak, 1987). Each card has three numbers:

- **repetitions**: how many times in a row you got it right,
- **ease**: how quickly its interval grows (starts at 2.5, never below 1.3),
- **interval**: days until you see it again.

When you grade a card:

1. **Pass** (Hard, Good or Easy): the interval becomes 1 day the first time,
   6 days the second time, and after that *previous interval × ease*.
2. **Fail** (Again): repetitions reset to 0 and the card comes back tomorrow.
3. **Either way the ease is adjusted**: Easy +0.10, Good unchanged, Hard −0.14,
   Again −0.54. Cards you find hard therefore grow their intervals more slowly.

The four buttons map onto SM-2's 0–5 quality scale as Again = 1, Hard = 3,
Good = 4, Easy = 5. Answering the same way every time gives these intervals
(these exact sequences are unit tests in [`tests/test_sm2.py`](tests/test_sm2.py)):

| Always pressing | Intervals (days)       | Ease afterwards        |
|-----------------|------------------------|------------------------|
| Easy            | 1, 6, 16, 45, ...      | 2.6, 2.7, 2.8, 2.9     |
| Good            | 1, 6, 15, 38, ...      | 2.5 (unchanged)        |
| Hard            | 1, 6, 13, 27, ...      | 2.36, 2.22, 2.08, 1.94 |

Intervals are rounded half-up (37.5 becomes 38). A card graded Again comes back
the next day rather than later in the same session.

## Where data lives and how edits are handled

| Path                         | Contents                                                 |
|------------------------------|----------------------------------------------------------|
| `~/memento/` (or `--deck`, `$MEMENTO_DECK`) | Your `.md` card files                     |
| `<deck>/.memento.db`         | SQLite: `cards` (current schedule of each reviewed card), `reviews` (append-only log of every answer), `schema_migrations` |

A card is linked to its schedule by an **id**: a short SHA-256 hash of its file path
(relative to the deck) and its *normalised* question (Unicode NFC, case-folded,
whitespace collapsed). Nothing is ever written into your Markdown. As a result:

| You...                                        | Result                                   |
|-----------------------------------------------|------------------------------------------|
| edit an answer or its tags                    | same card, history kept                  |
| fix capitalisation or spacing in a question   | same card, history kept                  |
| reword a question                             | a new card; the old schedule is ignored  |
| rename the file or move the card to another file | a new card                            |
| delete a card                                 | its schedule is ignored                  |
| undo any of the above                         | the old history is picked up again       |

Ignored schedules stay in the database until you run `memento check --prune`.
New cards have no database row at all until their first review.

Whether to commit `.memento.db` is up to you: commit it to sync progress
between machines, or add it to `.gitignore` to keep only the cards in git.

## Architecture

```
            Markdown files ──► parser ──► Card objects ─┐
                                                        ├─► scheduler ──► review session ──► store (SQLite)
                     store (SQLite) ──► CardState ──────┘        ▲
                                                               sm2
```

| Module                      | Responsibility                                                        |
|-----------------------------|-----------------------------------------------------------------------|
| `src/memento/parser.py`     | Markdown text → `Card` objects; card ids. Pure, no I/O.               |
| `src/memento/deck.py`       | Finds `.md` files in the deck directory and parses them.             |
| `src/memento/sm2.py`        | The SM-2 algorithm and the 1–4 grade mapping. Pure.                  |
| `src/memento/scheduler.py`  | Turns intervals into due dates; builds the review queue with limits. Pure. |
| `src/memento/store.py`      | SQLite: migrations, card state, review log, orphan pruning.         |
| `src/memento/review.py`     | The interactive session; takes a key-reader function and a rich `Console`. |
| `src/memento/stats.py`      | Computes statistics (pure) and renders them as tables.              |
| `src/memento/lint.py`       | The rules behind `memento check`.                                    |
| `src/memento/authoring.py`  | `memento add`: safe, verified appends and the `$EDITOR` flow.       |
| `src/memento/clock.py`      | `SystemClock` and a `FixedClock` for deterministic tests.            |
| `src/memento/cli.py`        | argparse commands; `main()` accepts clock, console and key reader.   |

Design choices worth knowing:

- **Pure core, thin edges.** Parsing, SM-2, queue building and statistics take
  data in and return data out, so they are tested with exact numbers.
- **Injected I/O.** Nothing calls `datetime.now()` or reads the keyboard
  directly. Tests drive a full review session with scripted key presses and a
  frozen clock, and simulate "coming back tomorrow" with `clock.advance(days=1)`.
- **Every review is its own transaction**, so quitting mid-session loses nothing.
- **Versioned schema.** `schema_migrations` records applied migrations; a
  database from a newer Memento is refused instead of being corrupted.

## Development

```bash
git clone https://github.com/sifonaniefiok/memento
cd memento
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest              # run the test suite
ruff check .        # lint
memento --deck examples review   # try it on the example decks
```

CI runs `ruff check` and `pytest` on Ubuntu and macOS with Python 3.10, 3.11
and 3.12 (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Limitations

- A question is a single heading line; multi-line questions are not supported.
- Only `#`/`##` ATX headings are structural; setext headings (`===` / `---`
  underlines) are not recognised as titles or questions.
- Images and other media in answers are shown as Markdown, not rendered.
- Windows is not tested in CI. The key reader has a Windows code path
  (`msvcrt`) but it has not been verified.
- SM-2 is a classic, simple algorithm; newer ones (such as FSRS) schedule more
  efficiently but are harder to explain and tune.

## License

[MIT](LICENSE) © 2026 Sifon Aniefiok
