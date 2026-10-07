#!/usr/bin/env python3
"""
Stop hook: append new turns from the current transcript to a daily-rotated
session log in the memory dir. Tracks per-session line offset so each Stop
only appends what's new since the last firing.

Reads hook JSON from stdin: { session_id, transcript_path, ... }
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Project slug Claude Code uses for $HOME-rooted sessions, e.g. "-Users-you".
HOME_SLUG = str(Path.home()).replace("/", "-")
MEMORY_DIR = Path.home() / ".claude/projects" / HOME_SLUG / "memory"
STATE_FILE = MEMORY_DIR / ".session_log_state.json"
LOG_DIR = MEMORY_DIR / ".session-logs"  # transient continuity logs, kept out of the recalled brain
MAX_TEXT_CHARS = 8000

SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
COMMAND_TAG_RE = re.compile(r"<(command-name|command-message|command-args|local-command-stdout|local-command-stderr)>.*?</\1>", re.DOTALL)


def clean(text: str) -> str:
    text = SYSTEM_REMINDER_RE.sub("", text)
    text = COMMAND_TAG_RE.sub("", text)
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n…[truncated {len(text) - MAX_TEXT_CHARS} chars]"
    return text


def extract_user(content) -> str | None:
    if isinstance(content, str):
        return clean(content) or None
    if isinstance(content, list):
        if all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return clean("\n".join(parts)) or None
    return None


def extract_assistant(content) -> str | None:
    if isinstance(content, str):
        return clean(content) or None
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                parts.append(block.get("text", ""))
            elif t == "tool_use":
                name = block.get("name", "?")
                parts.append(f"[tool: {name}]")
            elif t == "thinking":
                continue
        return clean("\n".join(parts)) or None
    return None


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    session_id = payload.get("session_id", "unknown")
    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    state = load_state()
    last_line = state.get(session_id, 0)

    new_entries: list[tuple[str, str]] = []
    line_count = 0
    with open(transcript_path) as f:
        for line in f:
            line_count += 1
            if line_count <= last_line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            etype = entry.get("type")
            msg = entry.get("message", {})
            if etype == "user":
                text = extract_user(msg.get("content", ""))
                if text:
                    new_entries.append(("user", text))
            elif etype == "assistant":
                text = extract_assistant(msg.get("content", []))
                if text:
                    new_entries.append(("assistant", text))

    state[session_id] = line_count
    save_state(state)

    if not new_entries:
        sys.exit(0)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"session_log_{today}.md"

    header_needed = not log_path.exists()
    with open(log_path, "a") as f:
        if header_needed:
            f.write(f"# Session log — {today}\n\n")
            f.write("Raw transcript appended on each Stop hook. System reminders stripped, tool calls noted as `[tool: Name]`.\n\n")
        f.write(f"---\n### {datetime.now().strftime('%H:%M:%S')} · session `{session_id[:8]}`\n\n")
        for role, text in new_entries:
            label = "**User:**" if role == "user" else "**Claude:**"
            f.write(f"{label}\n\n{text}\n\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
