# claude-code-setup

My Claude Code build: hooks, subagents, a mod, a skill, a CLAUDE.md, and the settings
that wire them together. macOS-first (the sound and one fallback path use macOS
built-ins), terminal-agnostic: tested on Ghostty, also handles Apple Terminal and iTerm2.

## Install

```bash
git clone https://github.com/lrendina/claude-code-setup.git
cd claude-code-setup
./install.sh
```

`install.sh` copies everything into `~/.claude`, backing up any file it replaces. It
merges `settings.snippet.json` into your `~/.claude/settings.json` with
`merge-settings.py`, which only adds what's missing. Your existing values win, a
timestamped backup is written first, and it refuses to touch a settings file that
isn't valid JSON. An existing `~/.claude/CLAUDE.md` is never overwritten.

Then:

1. Edit `~/.claude/CLAUDE.md`: put your name in, add your own rules.
2. `touch ~/.claude-bell` if you want a sound when a turn finishes or needs you.
3. Restart your Claude Code sessions.

Requirements: `python3`; the `claude` CLI on `PATH` (the retitle hook uses it to call
Haiku); Node is not needed.

## What's in it

### Hooks (`hooks/`)

| Hook | Event | What it does |
|---|---|---|
| `cook-color.py` | UserPromptSubmit / Stop / Notification / SessionEnd | Tints the terminal background by session state: navy while working, green when done, amber when it needs you, restored on exit. With ten windows open, you find the one that wants you by color. OSC 11 on Ghostty/iTerm2; per-tab AppleScript on Apple Terminal (only when you're actually in it). Off switch: `touch ~/.claude-nocolor`. |
| `retitle-window.py` | Stop | Claude Code names the tab once, from your first prompt, and never updates it. This regenerates a ≤5-word title from the recent conversation every turn using Haiku via your existing `claude` login (no API key), and writes it with OSC 2. It double-forks, so the turn never waits on it. Add `PROJECT_TAGS` rows to prefix titles per project. |
| `log-session.py` | Stop | Appends every turn of every session to a daily markdown log in `~/.claude/projects/<home-slug>/memory/.session-logs/`. That's your audit trail: `grep -rin '<term>'` that folder to find the exact prompt and the exact change. |
| `surface-recent-session.py` | SessionStart | Injects a ~4,000-char tail of the latest session logs into a new session, so it starts with context instead of blind. It pairs with `log-session.py`. |
| `auto-allow-prefixed-bash.py` | PreToolUse (Bash) | The permission allowlist matches the literal command, so `Bash(vercel ls:*)` doesn't match `WORK_ACCOUNT=acme vercel ls`. This strips known-harmless env prefixes and auto-allows the command if what's left is known read-only. Edit `SAFE_STRIPPED` to extend it. |
| `plan-gate/` | UserPromptSubmit + PreToolUse (Edit/Write) | Checkpoint locks for multi-phase plans. Edits that belong to a plan step you haven't unlocked get denied, or turned into a permission prompt when the classifier is unsure. `unlock <gate>` / `lock <gate>` on its own line always works. Uses the [TypeSafe](https://typesafe.ai) API (`TYPESAFE_API_KEY`). It's inert until you add a config: copy `~/.claude/plan-gates/example.json.disabled` to `<name>.json` and fill it in. `decision_check.py` is the companion "is this my call or yours?" checker for assumptions. |
| `chime.sh` | (not wired by default) | Cross-platform notification sound (macOS / Linux / WSL). The snippet uses a simpler `afplay` line gated on `~/.claude-bell`; swap this in if you're not on macOS. |

### Settings (`settings.snippet.json`)

- Wires the hooks above.
- `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` stops Claude Code from rewriting the tab title,
  which would otherwise overwrite `retitle-window.py` within seconds. You lose the
  spinner glyph in the tab title; `cook-color.py` shows the same state as color.
- `CLAUDE_CODE_PLUGIN_DIRS` loads the token-weather mod.
- Output style `Concise`, fullscreen TUI, dark theme, per-model effort levels,
  advisor on `fable`, push notifications on.
- `autoMode.soft_deny`: force-push and Vercel prod deploy/promote/alias/rollback need an
  explicit instruction.
- Plugins: `vercel` (official marketplace), `typesafe`, `impeccable`.

### Subagents (`agents/`)

- **explorer**: read-only codebase exploration.
- **researcher**: external docs and API lookups.
- **worker**: implements an already-planned change, plus its tests.

All three run on Opus at medium effort.

### Mod (`mods/token-weather/`)

A live "forecast" of the context window in the band above the prompt: a sparkline of
recent fill, percentage, delta, and a weather word that goes from ☀ Clear to ↯ Compact
soon as you approach the limit. Tests: `claude plugin test ~/.claude/mods/token-weather`.

### Skill (`skills/token-efficient-work/`)

Rules for keeping context small during long multi-step work. Locate before reading,
look at the shape of a diff before its hunks, pipe long output, and don't re-read what
you just wrote.

### CLAUDE.md

Global instructions, mostly about output: answer first, a **Need from you:** block at
the top, numbered steps, matter-of-fact errors, no closers. Also: dev-server port
discipline, the memory-directory convention, safe settings.json edits, when to consult
the advisor, and a few git and deploy guardrails.

### Memory (`memory/MEMORY.md`)

The empty router index. Claude Code auto-loads it each session. One line per memory,
each linking to a one-fact file with frontmatter.

### Reference (`reference/settings-and-hooks.md`)

A hooks and settings cheat sheet that CLAUDE.md points Claude to when it's writing or
debugging hooks.

## Skills and plugins I use but don't vendor

These are other people's work; install them from their sources:

- Plugins: `vercel@claude-plugins-official`, `typesafe@typesafe-ai`
  ([typesafe-ai/skills](https://github.com/typesafe-ai/skills)), `impeccable@impeccable`
  ([pbakaus/impeccable](https://github.com/pbakaus/impeccable)). The marketplaces are
  already declared in the snippet.
- Skills: the taste-skill design set (`design-taste-frontend`, `high-end-visual-design`,
  `minimalist-ui`, `industrial-brutalist-ui`, `gpt-taste`, `image-to-code`, …),
  `find-skills`, `agentation`, `fluid-functionalism`.

## Credits

`cook-color.py`, `retitle-window.py`, `log-session.py`, `surface-recent-session.py` and
`auto-allow-prefixed-bash.py` started life in a friend's `cc-setup-bundle`, shared
alongside [davinpatel21/cc-switcher-oss](https://github.com/davinpatel21/cc-switcher-oss).
I've modified them since: `retitle-window.py` now titles tabs over OSC instead of
AppleScript-driving Terminal.app, which used to launch Terminal in the background on
every turn.

## License

MIT for my own work in this repo (see `LICENSE`). The credited hooks above remain their
author's.
