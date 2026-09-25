# docs/backlog/todo/ — pending work

This file is **only the map**: it explains the folder's convention and lists
what lives here. No task item lives in it — each line of work has its own
file, so a session opens only what it needs.

## Organization rules

- **One file per goal.** A numbered backlog is `backlog-NN.md`; any other
  line of work (an isolated piece of tech debt, an audit) gets a descriptive
  kebab-case name.
- **Every file opens with a title and one line of context** pointing to this
  index, because any of them may be opened on its own.
- **A file only leaves this folder 100% done**, whole, to
  [../done/](../done/), with "resolved on …" on every item that did not have
  it yet. While any item is open, the file stays here — `[x]` items included —
  so the reasoning behind each decision is not lost and cross-references do
  not break.
- **Do not split a large file into smaller ones** to fit the convention; the
  one-goal-per-file cut applies to new work.
- If a change closes an item in ANOTHER file (or in another repo of the
  ecosystem), close it there too, with date and context.
- When a file is closed, move its line from this index to the `done/` one in
  the same commit.

Workflow (branch, commit, version, changelog) lives only in
[CLAUDE.md](../../../CLAUDE.md) — it is not repeated here.

## Index

| File | What it covers |
| --- | --- |
| [backlog-01.md](backlog-01.md) | Restart (opened on 2026-09-24): consolidate the WIP, get `make check` green, fix the bugs found in the survey and present the repo as a showcase |
| [backlog-02.md](backlog-02.md) | Axiom Flow reaches the application: use cases that connect FlowEngine, TaskLanguageEngine and learning to the rest of the system |
