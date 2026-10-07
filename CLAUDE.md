Start every message with my name (<YOUR NAME>).

## Hard rules

- **Never `git add -A` without checking the branch first.** `git branch` then
  `git status` before every commit.
- **No prod deploys without being told.** No `vercel --prod`, no promote, no alias, no
  rollback unless the ask was explicit.
- **Never smoke-test a write endpoint in prod.** Verify a deployed POST with a payload
  that FAILS validation. A valid one runs every side effect.

## How I want output

1. First line is the action or the answer. No preamble.
2. Anything I have to do goes at the top under **Need from you:**, numbered.
3. Links and file paths stated plainly, at the top, not buried.
4. More than one step means a numbered list.
5. Errors are matter-of-fact: what failed, where, cause, fix.
6. No closers, no "hope this helps", no recap of what you just did.

## Dev server ports

Before starting any dev server, check what is already listening:

```
lsof -iTCP -sTCP:LISTEN -nP | grep -E ':(3[0-9]{3}|4[0-9]{3}|5[0-9]{3}) '
```

Pick the first free port from: 3000, 3100, 3200, 3300, 3400, 3500. Always pass it
explicitly (`--port 3100`). Never start on a port that is already listening.

## Memory

Persistent notes live in `~/.claude/projects/-Users-<you>/memory/`. One fact per file,
with frontmatter. `MEMORY.md` in that directory is the index — it auto-loads every
session, so it holds one-line pointers only, never content.

Write a memory when: you got corrected and the correction generalizes; you learned a
non-obvious constraint about the system; you found a gotcha that cost you an hour. Do
not write memories for things the repo already records.

## Settings & hooks
- Before editing any settings.json: read it first and merge into existing arrays, never replace the file. Malformed JSON silently disables every setting in that file.
- Full hook and settings reference: ~/.claude/reference/settings-and-hooks.md. Read it only when writing or debugging hooks.

## Advisor
- Consult the advisor (1) before committing to a plan that spans several files or steps,
  (2) the second time the same error shows up, and (3) before calling a long task done.

## Full Setting Schema
See https://json.schemastore.org/claude-code-settings.json for the complete schema. Consult it directly when validating or authoring settings.json.
