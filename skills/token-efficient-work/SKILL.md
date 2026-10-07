---
name: token-efficient-work
description: Keep context small during long multi-step repo work — code review, audits, migrations, phased builds. Use when reading diffs or docs, running verification (typecheck/lint/build/browser scripts), or when a session will span many edits, checks and commits.
---

# Token-efficient work

Context is the budget. Everything pulled into it — file dumps, verbose command output, failed
retries — is re-sent on every later turn. A 50KB file read once costs for the rest of the
session. Optimise for the smallest artifact that answers the question.

## Read narrowly

- **Locate, then read.** `grep -rn "pattern" path` first; open only the matching range with
  `sed -n '120,180p'` or Read with `offset`/`limit`.
- **Never `cat` a file over ~100 lines** to "get oriented". Read its headings
  (`grep -n "^#" doc.md`), then the section you need.
- **Diffs: shape first.** `git diff --stat`, then `git diff -- path/to/one/file`. Reviewing a
  large changeset rarely needs every hunk in context at once.
- **Persisted tool output is a file, not a must-read.** When a command's output is saved
  because it was too large, grep that file. Reading it whole re-imports exactly what the
  harness just spared you.
- **Don't re-read what you just wrote.** Edit and Write already report success.

## Keep command output small

- Pipe long output: `| head -20`, `| tail -5`, `| cut -c1-200`.
- Collapse repetition: `sort | uniq -c`, or print counts and the first two examples. A checker
  listing 16 near-identical failures makes its point in 2.
- Prefer booleans and counts over dumps: `grep -c`, `test ... && echo ok`, a one-line summary
  per route instead of a JSON blob.
- Print what you will act on. Full JSON reports are worth it once, not per iteration.

## Batch the work

- **One verification pass per phase, not per fix.** Chain it:
  `npx tsc --noEmit && npm run lint && npm test && npm run build`, and read only the tail.
- Make every edit to a file in one pass. Each separate edit can echo the changed file back
  into context.
- Group related fixes, then verify, then commit. Micro cycles of edit → verify → commit
  multiply the fixed cost of each turn.
- Write verification scripts **to a file once** (`scripts/audit.mjs`, or a scratch dir) and
  rerun with arguments. Never re-author a near-duplicate script inline.

## Avoid retries — they cost double

- **zsh does not word-split unquoted variables.** `$FILES` is one argument. Use arrays
  (`files=(a b); cmd "${files[@]}"`) or explicit paths.
- **Quote glob arguments**: `--include='*.ts'`, or the shell expands them first.
- **`$` in a grep pattern is an anchor.** Use `grep -F` for literals like `$153,823`.
- **Regex on one line vs many.** Minified HTML and single-line files defeat `sed` ranges; use
  `perl -0ne` with a non-greedy match, or index-based slicing.
- **Dry-run destructive rewrites.** `grep -c 'pattern' file` before `perl -pi -e 's/…/…/'`,
  then verify the result. A line-mode substitution touching `\n` can silently join lines.
- After any scripted edit, confirm it landed (`grep -n`). A pattern that matched nothing is a
  silent no-op you will otherwise discover three steps later.

## Browser and long-running checks

- Keep a scripted browser pass **well under the tool timeout** (~45s). Budget every `sleep`.
- Cap every wait: `Promise.race([event, timeout])` so a missed event cannot hang the call.
- Background/hidden tabs throttle timers and observers — results look like bugs. Drive pages
  from a script (headless) rather than a tab that lost focus.
- Set `scroll-behavior: auto` before scripted scrolling, or measurements race the animation.
- Never rebuild while a dev or production server serves that build directory; stop it first.

## Rules of thumb

- Ask: "what is the smallest output that would change my next action?" Fetch that.
- Two targeted greps beat one file dump.
- If you have read a file twice in a session, you needed a grep both times.
- Long sessions: a handful of decisive checks beats a long tail of confirmations.
