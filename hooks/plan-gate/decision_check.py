#!/usr/bin/env python3
"""Hook B: "is this my call or yours?"

Usage (from inside the gated checkout):
    python3 ~/.claude/hooks/plan-gate/decision_check.py assumptions.txt   # one assumption per line

For each assumption, one request asks a Choice per plan bullet: does the bullet
settle the assumption the same way, contradict it, or leave it open?
  SETTLED  - some bullet settles it (>= SETTLED_AT) and none contradicts it
  CONFLICT - some bullet contradicts it (>= CONFLICT_AT): show the user both
  ASK      - nothing settles it: it goes under "Need from you" in the checkpoint report
Every miss routes to the user; nothing is ever decided by this script.
Exit code 1 when anything is CONFLICT, ASK or ERROR.
"""
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SETTLED_AT, CONFLICT_AT = 0.8, 0.5


def plan_bullets(plan_path, skip_sections):
    bullets, section = [], ""
    with open(plan_path) as f:
        for line in f:
            if line.startswith("#"):
                section = line.strip("# \n")
                continue
            m = re.match(r"\s*(?:[-*]|\d+\.)\s+(?:\[[ x]\]\s+)?(.*)", line)
            if m and len(m.group(1)) > 15 and not section.startswith(tuple(skip_sections)):
                bullets.append(f"[{section}] {m.group(1).strip()}")
    return bullets


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cfg_path, cfg = common.find_config(os.getcwd())
    if not cfg:
        sys.exit("No active plan-gate config for this checkout.")
    bullets = plan_bullets(cfg["plan_path"], cfg.get("decision_skip_sections", []))
    questions = {f"b{i}": {
        "type": "choice",
        "instructions": {
            "plan_bullet": b,
            "question": ("An AI agent building this plan wants to act on the assumption in the state. "
                         "How does `plan_bullet` relate to that assumption?"),
        },
        "criteria": {
            "settles_same": "The bullet explicitly decides this same point, the same way, so the agent may act on the assumption without asking.",
            "contradicts": "The bullet decides this same point differently from the assumption.",
            "open_or_unrelated": "The bullet is about something else, only touches the topic, or leaves this point undecided or pending.",
        },
    } for i, b in enumerate(bullets)}

    def check(text):
        try:
            out = common.ask_jev(cfg, {"assumption": text}, questions, timeout=30)
        except Exception as e:
            return text, "ERROR", str(e), None, None
        best_s, best_c = (0.0, None), (0.0, None)
        for qid, a in out["answers"].items():
            pr, i = a.get("probabilities") or {}, int(qid[1:])
            if pr.get("settles_same", 0) > best_s[0]:
                best_s = (pr["settles_same"], i)
            if pr.get("contradicts", 0) > best_c[0]:
                best_c = (pr["contradicts"], i)
        verdict = ("CONFLICT" if best_c[0] >= CONFLICT_AT
                   else "SETTLED" if best_s[0] >= SETTLED_AT else "ASK")
        return text, verdict, None, best_s, best_c

    with open(sys.argv[1]) as f:
        lines = [line.strip() for line in f if line.strip()]
    failed = False
    with ThreadPoolExecutor(5) as ex:
        for n, (text, verdict, err, s, c) in enumerate(ex.map(check, lines), 1):
            common.log_event(cfg_path, {"event": "decision", "assumption": text, "verdict": verdict,
                                        "settles": s and round(s[0], 3), "contradicts": c and round(c[0], 3)})
            print(f"{n:2d}. {verdict:8} {text}")
            failed |= verdict != "SETTLED"
            if err:
                print(f"      error: {err}")
            elif verdict == "SETTLED":
                print(f"      by ({s[0]:.2f}): {bullets[s[1]][:150]}")
            elif verdict == "CONFLICT":
                print(f"      vs ({c[0]:.2f}): {bullets[c[1]][:150]}")
            elif s[1] is not None:
                print(f"      nearest ({s[0]:.2f}): {bullets[s[1]][:110]}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
