# docs/backlog/done/ — history of finished work

This file is **only the map**: it explains the folder's convention and indexes
what has been closed, so a session does not need to open the large files just
to find out where a subject lives.

## Organization rules

- **One file per closed goal**, which arrives here whole, after being 100%
  done in [../todo/](../todo/README.md).
- **No retroactive edits**, except to fix a record error (date, link) or a
  translation. The file exists so closed decisions are not reopened.
- Every file opens with `# Name ✅ (date)` and one line pointing to this
  index.
- Each table row is **one sentence**, enough to decide whether the file is
  worth opening. When something is closed, add its row here in the same
  commit.

## How to search without blowing the context

1. Start with the table below.
2. Without knowing the file: `grep -rn "term" docs/backlog/done/`.
3. Inside a file: `grep -n "^#\{1,2\} "` for the sections, `sed -n 'A,Bp'`
   for the excerpt.

## Index

| File | Period | What it covers |
| --- | --- | --- |

Nothing closed yet. The work before the restart (Mar–Jun 2026) is
summarized in [CHANGELOG.md](../../../CHANGELOG.md).
