#!/usr/bin/env python3
"""Tint the terminal background by Claude Code session state.

Usage: cook-color.py <cooking|done|waiting|restore>

Wired to hooks:
  UserPromptSubmit -> cooking   (dark neutral, "stove is on")
  Stop             -> done      (dark green,  "come look")
  Notification     -> waiting   (dark amber,  "needs you")
  SessionEnd       -> restore   (whatever the tab was before)

Off switch: touch ~/.claude-nocolor
Works on Apple Terminal (AppleScript, per-tab) and iTerm2/others (OSC 11).

Optional violet mode: if ~/.claude/state/prompt-mode/<session_id> exists, the
window shifts to a VIOLET family instead of the usual navy/green/amber, so one
flagged window is unmistakable next to the rest. Nothing in this bundle creates
that directory — the branch simply never fires unless you wire up something that
does. Safe to ignore, or delete PROMPT_STATES and in_prompt_mode() if it bugs you.
"""
import json
import os
import re
import subprocess
import sys

STATES = {
    "cooking": (0x0D, 0x15, 0x26),   # baseline-ish navy
    "done":    (0x0B, 0x2E, 0x18),   # dark green
    "waiting": (0x38, 0x26, 0x08),   # dark amber
}

# prompt-mode window: violet family, same brightness ladder as STATES
PROMPT_STATES = {
    "cooking": (0x1A, 0x10, 0x36),   # dark violet
    "done":    (0x2E, 0x18, 0x5C),   # violet, "come look"
    "waiting": (0x46, 0x16, 0x50),   # violet-magenta, "needs you"
}

STATE_DIR = os.path.expanduser("~/.claude/.cook-color")
PROMPT_MODE_DIR = os.path.expanduser("~/.claude/state/prompt-mode")

# same toggle grammar as prompt-mode.py, so the very turn that flips the mode
# already paints the right color (hooks run in parallel, flag may not exist yet)
_TOGGLE = re.compile(r"^\s*/?\s*prompt[\s_-]*mode\s*(on|off)\s*[.!]?\s*$", re.IGNORECASE)
_EXIT = re.compile(r"^\s*(exit|leave|stop)\s+prompt\s*mode\s*[.!]?\s*$", re.IGNORECASE)


def read_payload():
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def in_prompt_mode(payload):
    prompt = payload.get("prompt") or ""
    if _EXIT.match(prompt):
        return False
    m = _TOGGLE.match(prompt)
    if m:
        return m.group(1).lower() == "on"
    sid = payload.get("session_id")
    return bool(sid) and os.path.exists(os.path.join(PROMPT_MODE_DIR, sid))


def palette(payload):
    return PROMPT_STATES if in_prompt_mode(payload) else STATES


def parent_tty():
    """Walk up the process tree until a real tty shows up."""
    pid = os.getppid()
    for _ in range(8):
        try:
            out = subprocess.run(
                ["ps", "-o", "tty=,ppid=", "-p", str(pid)],
                capture_output=True, text=True, timeout=3,
            ).stdout.split()
        except Exception:
            return None
        if len(out) < 2:
            return None
        tty, ppid = out[0], out[1]
        if tty not in ("??", "-"):
            return "/dev/" + tty
        pid = int(ppid)
        if pid <= 1:
            return None
    return None


def osa(script):
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def term_get_bg(tty):
    out = osa(f'''tell application "Terminal"
  repeat with w in windows
    repeat with t in tabs of w
      if (tty of t) is "{tty}" then
        set c to background color of t
        return ((item 1 of c) as string) & " " & ((item 2 of c) as string) & " " & ((item 3 of c) as string)
      end if
    end repeat
  end repeat
end tell''')
    if not out:
        return None
    nums = [int(x) for x in out.replace(",", " ").split() if x.strip().isdigit()]
    return nums[:3] if len(nums) >= 3 else None


def term_set_bg(tty, rgb16):
    r, g, b = rgb16
    osa(f'''tell application "Terminal"
  repeat with w in windows
    repeat with t in tabs of w
      if (tty of t) is "{tty}" then set background color of t to {{{r}, {g}, {b}}}
    end repeat
  end repeat
end tell''')


def baseline_path(tty):
    return os.path.join(STATE_DIR, tty.replace("/", "_") + ".json")


# --- profile-switching path (keeps the theme's alpha/blur/font intact) ------
# For a base profile "X", tinted siblings are named "X_done", "X_waiting",
# "X_p-cooking", "X_p-done", "X_p-waiting" (imported .terminal files, see
# ~/.claude/.cook-color/profiles/). Cooking in normal mode = the base itself.
_SUFFIXES = ("_p-cooking", "_p-done", "_p-waiting", "_done", "_waiting")


def _q(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def term_get_profile(tty):
    out = osa(f'''tell application "Terminal"
  repeat with w in windows
    repeat with t in tabs of w
      if (tty of t) is "{tty}" then return name of current settings of t
    end repeat
  end repeat
end tell''')
    return out or None


def term_set_profile(tty, name):
    # Swapping profiles also applies the profile's stored font size (12pt), and
    # Terminal keeps the grid, so a tab magnified by ⌘+ or TermTidy would shrink
    # on every turn. Carry the tab's own size across the swap.
    osa(f'''tell application "Terminal"
  repeat with w in windows
    repeat with t in tabs of w
      if (tty of t) is "{tty}" then
        set fs to font size of t
        set current settings of t to settings set "{_q(name)}"
        if (font size of t) is not fs then set font size of t to fs
      end if
    end repeat
  end repeat
end tell''')


def term_profile_names():
    out = osa('tell application "Terminal" to get name of every settings set')
    return [x.strip() for x in out.split(",")] if out else []


def base_profile_name(name):
    for s in _SUFFIXES:
        if name.endswith(s):
            return name[: -len(s)]
    return name


def profile_for(base, state, prompt):
    if state == "cooking" and not prompt:
        return base
    return f"{base}_{'p-' if prompt else ''}{state}"


def main():
    if os.path.exists(os.path.expanduser("~/.claude-nocolor")):
        return
    state = sys.argv[1] if len(sys.argv) > 1 else "done"
    payload = read_payload()
    prompt = in_prompt_mode(payload)
    states = PROMPT_STATES if prompt else STATES
    tty = parent_tty()
    if not tty:
        return

    os.makedirs(STATE_DIR, exist_ok=True)
    bp = baseline_path(tty)

    if os.environ.get("TERM_PROGRAM") == "Apple_Terminal":
        # Preferred: switch the tab's profile to a tinted sibling so the
        # theme's transparency/blur/font survive. Falls through to the raw
        # color path when no sibling profiles exist for this base.
        saved = None
        if os.path.exists(bp):
            try:
                with open(bp) as f:
                    saved = json.load(f)
            except Exception:
                saved = None
        if isinstance(saved, dict) and "profile" in saved:
            base = saved["profile"]
        elif saved is None:
            cur = term_get_profile(tty)
            base = base_profile_name(cur) if cur else None
        else:
            base = None  # legacy color-only baseline
        if base:
            names = term_profile_names()
            if f"{base}_done" in names:
                if not (isinstance(saved, dict) and "profile" in saved):
                    with open(bp, "w") as f:
                        json.dump({"profile": base}, f)
                if state == "restore":
                    term_set_profile(tty, base)
                    try:
                        os.remove(bp)
                    except Exception:
                        pass
                    return
                target = profile_for(base, state, prompt)
                if target in names:
                    term_set_profile(tty, target)
                return

        if not os.path.exists(bp):
            base = term_get_bg(tty)
            if base:
                with open(bp, "w") as f:
                    json.dump(base, f)
        if state == "restore":
            try:
                with open(bp) as f:
                    base = json.load(f)
                term_set_bg(tty, base)
                os.remove(bp)
            except Exception:
                pass
            return
        rgb = states.get(state)
        if rgb:
            term_set_bg(tty, [c * 257 for c in rgb])
        return

    # iTerm2 / anything else that honors OSC 11
    if state == "restore":
        seq = "\033]111\007"
    else:
        rgb = states.get(state)
        if not rgb:
            return
        seq = "\033]11;#%02x%02x%02x\007" % rgb
    try:
        with open(tty, "w") as f:
            f.write(seq)
    except Exception:
        pass


if __name__ == "__main__":
    main()
