# Git

Everyday Git commands worth knowing by heart. Try them with:
`memento review --deck examples`

## How do you stage only some of the changes in a file?
tags: git, staging

```bash
git add -p path/to/file
```

Git walks through each change ("hunk") and asks whether to stage it:
`y` yes, `n` no, `s` split into smaller hunks, `q` quit.

---

## What is the difference between `git fetch` and `git pull`?
tags: git, remotes

- `git fetch` downloads new commits from the remote but does **not** touch
  your working branch.
- `git pull` is `git fetch` followed by a merge (or a rebase with
  `--rebase`) into your current branch.

---

## How do you undo the last commit but keep its changes?
tags: git, undo

```bash
git reset --soft HEAD~1
```

The commit disappears, and its changes stay staged so you can fix and
recommit them. Use `--mixed` (the default) to keep them unstaged instead.

---

## How do you see what changed in each commit, with the diff?
tags: git, history

```bash
git log -p
## add -- path/to/file to limit it to one file
```

---

## What does `git stash` do?
tags: git

It saves your uncommitted changes on a stack and returns the working tree to
the last commit. `git stash pop` reapplies the most recent stash.
