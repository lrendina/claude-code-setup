#!/usr/bin/env python3
"""
SessionStart hook: surface a tail of the most recent session log(s) so Claude
resumes with prior context instead of starting blind.

Pairs with log-session.py (the Stop hook that writes these logs). Output is
bounded to ~MAX_CHARS to keep token cost low, and spans into older logs only
when the newest one is sparse (e.g. just after a day rollover).
"""
import sys
from pathlib import Path

HOME_SLUG = str(Path.home()).replace("/", "-")
LOG_DIR = Path.home() / ".claude/projects" / HOME_SLUG / "memory/.session-logs"
MAX_CHARS = 4000  # ~1k tokens of continuity context


def main() -> None:
    # SessionStart may pass JSON on stdin; we don't need it. Drain so we never block.
    try:
        sys.stdin.read()
    except Exception:
        pass

    if not LOG_DIR.exists():
        return
    logs = sorted(LOG_DIR.glob("session_log_*.md"))
    if not logs:
        return

    # Walk newest-first, pulling tails until the char budget is spent.
    budget = MAX_CHARS
    chunks: list[tuple[Path, str, bool]] = []
    for log in reversed(logs):
        if budget <= 0:
            break
        try:
            text = log.read_text(errors="replace")
        except Exception:
            continue
        take = text[-budget:]
        truncated = len(text) > len(take)
        chunks.append((log, take, truncated))
        budget -= len(take)

    if not chunks:
        return

    print("=== Session continuity — most recent activity ===")
    print(f"Logs live in: {LOG_DIR}")
    print(f"To search all history: grep -rin '<term>' {LOG_DIR}")
    print("This is a tail of the latest log(s) so you can resume. Read the full")
    print("file(s) for more — DO NOT claim no prior context exists without checking.")
    print()

    # Print oldest-first so the excerpt reads chronologically into the present.
    for log, take, truncated in reversed(chunks):
        print(f"----- {log.name}" + (" (earlier truncated)" if truncated else "") + " -----")
        print(take.strip())
        print()


if __name__ == "__main__":
    main()
