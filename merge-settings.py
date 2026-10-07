#!/usr/bin/env python3
"""Merge settings.snippet.json into ~/.claude/settings.json without replacing it.

- hooks: per event, appends each snippet hook whose command isn't already present.
- env / enabledPlugins / extraKnownMarketplaces / modelSettings: adds missing keys only.
- autoMode.soft_deny: appends missing entries.
- any other top-level key: set only if absent. Your existing values always win.

Backs up the original to settings.json.bak-<timestamp> and refuses to write
anything if the existing file isn't valid JSON (fix it first).
"""
import json
import os
import shutil
import sys
import time

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.snippet.json")
DEST = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/.claude/settings.json")


def commands(groups):
    return {h.get("command") for g in groups for h in g.get("hooks", [])}


def merge_hooks(cur, new):
    added = 0
    for event, groups in new.items():
        have = cur.setdefault(event, [])
        existing = commands(have)
        for g in groups:
            fresh = [h for h in g.get("hooks", []) if h.get("command") not in existing]
            if fresh:
                have.append({**g, "hooks": fresh})
                existing |= {h.get("command") for h in fresh}
                added += len(fresh)
    return added


def main():
    with open(SRC) as f:
        snip = json.load(f)
    if not os.path.exists(DEST):
        os.makedirs(os.path.dirname(DEST), exist_ok=True)
        shutil.copy(SRC, DEST)
        print(f"wrote {DEST} (no existing settings)")
        return
    try:
        with open(DEST) as f:
            cur = json.load(f)
    except ValueError as e:
        sys.exit(f"{DEST} is not valid JSON ({e}); fix it first, nothing written")

    added = merge_hooks(cur.setdefault("hooks", {}), snip.get("hooks", {}))
    for key in ("env", "enabledPlugins", "extraKnownMarketplaces", "modelSettings"):
        for k, v in snip.get(key, {}).items():
            cur.setdefault(key, {}).setdefault(k, v)
    deny = cur.setdefault("autoMode", {}).setdefault("soft_deny", [])
    for rule in snip.get("autoMode", {}).get("soft_deny", []):
        if rule not in deny:
            deny.append(rule)
    for k, v in snip.items():
        if k not in ("hooks", "env", "enabledPlugins", "extraKnownMarketplaces", "modelSettings", "autoMode"):
            cur.setdefault(k, v)

    backup = f"{DEST}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy(DEST, backup)
    out = json.dumps(cur, indent=2) + "\n"
    json.loads(out)  # never write something that won't parse
    with open(DEST, "w") as f:
        f.write(out)
    print(f"merged into {DEST} ({added} hook(s) added); backup at {backup}")


if __name__ == "__main__":
    main()
