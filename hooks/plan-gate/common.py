"""Shared helpers for the plan-gate hooks: config lookup, gate state, Jev calls, logging.

A checkout is gated only when a config in ~/.claude/plan-gates/*.json names its
top-level directory (one worktree, not the whole repo, so other worktrees of the
same repo are never gated by this plan). No config -> every hook exits at once.
Jev only ever moves a decision toward the user: it can block an edit or keep a
gate locked, and a gate unlocks from free text only above a high threshold.
"""
import datetime
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

CONFIG_DIR = os.path.expanduser("~/.claude/plan-gates")
API_URL = "https://api.typesafe.ai/v1/systemone"


def checkout_root(cwd):
    """Top-level directory of the checkout or worktree `cwd` is in."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def find_config(cwd):
    """Return (path, config) for the active gate config of this checkout, or (None, None)."""
    if not os.path.isdir(CONFIG_DIR):
        return None, None
    root = checkout_root(cwd)
    if not root:
        return None, None
    for name in sorted(os.listdir(CONFIG_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CONFIG_DIR, name)
        try:
            with open(path) as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            continue
        if cfg.get("active") and os.path.realpath(cfg.get("checkout_root", "")) == os.path.realpath(root):
            return path, cfg
    return None, None


def save_config(path, cfg):
    """Atomic write so two sessions never leave a half-written state file."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_event(cfg_path, event):
    """Append one JSON line per decision; this is the tuning data for the thresholds."""
    event = {"at": now_iso(), **event}
    with open(cfg_path[:-5] + ".log.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")


def locked_gates(cfg):
    return [g for g in cfg["gates"] if not g.get("approved")]


def status_line(cfg):
    parts = [f"{g['id']}={'approved' if g.get('approved') else 'LOCKED'}" for g in cfg["gates"]]
    return f"Plan gates ({cfg['name']}): " + ", ".join(parts)


def load_key(cfg):
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key
    key_file = cfg.get("key_file")
    if key_file and os.path.exists(key_file):
        with open(key_file) as f:
            for line in f:
                m = re.match(r"\s*(?:export\s+)?TYPESAFE_API_KEY=(.*)", line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    raise RuntimeError("TYPESAFE_API_KEY not found in env or key_file")


def ask_jev(cfg, state, questions, timeout=6):
    """One System One request. Retries once on a network error or 429/5xx, then raises."""
    body = json.dumps({"model": cfg.get("model", "jev-1.13.0"), "state": state, "questions": questions}).encode()
    headers = {"Authorization": f"Bearer {load_key(cfg)}", "Content-Type": "application/json"}
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(API_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429 and e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        if attempt == 0:
            time.sleep(0.5)
    raise RuntimeError(f"Jev request failed: {last}")


def last_assistant_text(transcript_path, limit=600):
    """Tail of the agent's last message, so a bare 'yes' can be read against its question."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    text = ""
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("type") != "assistant":
                    continue
                content = (row.get("message") or {}).get("content") or []
                chunks = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                if any(chunks):
                    text = "\n".join(chunks)
    except OSError:
        return ""
    return text[-limit:]
