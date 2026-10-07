#!/usr/bin/env python3
"""Hook A: plan checkpoint lock.

UserPromptSubmit: a Noul per locked gate asks whether the user's message gives
permission to start it. At UNLOCK_AT or above the gate is approved and recorded.
`unlock <gate>` / `lock <gate>` on its own line always works without the model.

PreToolUse (Edit|Write|MultiEdit|NotebookEdit): a Choice decides which plan step an
edit belongs to. An edit that belongs to a locked step is denied (or sent to the user
as a permission prompt when Jev is less sure). The plan file itself is always writable.

What leaves the machine: the file path and up to EXCERPT chars of the change go to
the TypeSafe API. Env files send their path only. Every decision is appended to
~/.claude/plan-gates/<name>.log.jsonl for tuning; thresholds are untuned starting points.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

UNLOCK_AT = 0.9     # Noul probability needed to approve a gate from free text
DENY_AT = 0.8       # probability an edit belongs to a locked step -> deny
ASK_AT = 0.4        # between ASK_AT and DENY_AT -> permission prompt to the user
EXCERPT = 2000      # chars of the change sent to Jev
SECRET_FILE = re.compile(r"(^|/)\.env(\.|$)|\.(pem|key)$")

CHECK_HINT = ("Before a checkpoint report, list your assumptions and run "
              "`python3 ~/.claude/hooks/plan-gate/decision_check.py <file>` on them (hook B).")


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def on_prompt(data, cfg_path, cfg):
    prompt = data.get("prompt") or ""
    ids = {g["id"]: g for g in cfg["gates"]}
    notes, shown = [], []

    for m in re.finditer(r"(?im)^\s*(unlock|lock)\s+([a-z0-9_]+)\s*$", prompt):
        verb, gid = m.group(1).lower(), m.group(2)
        if gid not in ids:
            notes.append(f"Unknown gate '{gid}'.")
            continue
        g = ids[gid]
        g["approved"] = verb == "unlock"
        g["approved_at"] = common.now_iso() if g["approved"] else None
        g["approved_by"] = f"explicit '{verb} {gid}'"
        common.log_event(cfg_path, {"event": "manual", "gate": gid, "verb": verb})
        shown.append(f"{gid} {verb}ed by explicit command")

    locked = common.locked_gates(cfg)
    if locked and prompt.strip():
        agent_tail = common.last_assistant_text(data.get("transcript_path"))
        questions = {}
        for g in locked:
            questions[g["id"]] = {
                "type": "noul",
                "instructions": {
                    "context": (f"An AI coding agent follows a written plan ({cfg['plan_title']}) and must not start "
                                "`gate` until the user gives permission. Only the user's message can give permission; "
                                "the agent's last message is shown only so a short reply like 'yes' can be understood."),
                    "gate": {"name": g["title"], "work": g["work"]},
                    "question": "Does `user_message` give the agent permission to start `gate` now?",
                },
                "criteria": {
                    "true": ("The user tells the agent to go ahead now with this step or with the work it belongs to, "
                             "directly or by saying yes to the agent asking to start it, even if the message also "
                             "covers other topics or conditions that are already met."),
                    "false": ("The user only asks a question, gives feedback, approves a different step, tells the "
                              "agent to wait, or makes the go-ahead depend on something that has not happened yet."),
                },
            }
        state = {"user_message": prompt[-4000:], "agent_last_message_tail": agent_tail}
        try:
            out = common.ask_jev(cfg, state, questions)
            for g in locked:
                p = float(out["answers"][g["id"]]["noul"])
                common.log_event(cfg_path, {"event": "prompt", "gate": g["id"], "p": p, "prompt": prompt[:300]})
                if p >= UNLOCK_AT:
                    g["approved"] = True
                    g["approved_at"] = common.now_iso()
                    g["approved_by"] = f"user message (Jev p={p:.2f}): {prompt[:160]}"
                    shown.append(f"{g['id']} unlocked (p={p:.2f})")
                elif p >= 0.5:
                    notes.append(f"{g['id']} stays LOCKED (p={p:.2f}, below {UNLOCK_AT}). If the user meant to approve "
                                 f"it, ask them to confirm, or they can type 'unlock {g['id']}'.")
        except Exception as e:  # keep the lock as it was; never unlock on a failed read
            notes.append(f"Gate check failed, locks unchanged: {e}")
            common.log_event(cfg_path, {"event": "prompt_error", "error": str(e)})

    common.save_config(cfg_path, cfg)
    context = "\n".join([common.status_line(cfg), *[f"- {s}" for s in shown], *[f"- {n}" for n in notes], CHECK_HINT])
    result = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}
    if shown:
        result["systemMessage"] = "Plan gate: " + "; ".join(shown) + ". Type 'lock <gate>' to undo."
    emit(result)


def change_text(tool_input):
    if "content" in tool_input:
        return tool_input.get("content") or ""
    if "new_string" in tool_input:
        return f"REPLACE:\n{(tool_input.get('old_string') or '')[:600]}\nWITH:\n{tool_input.get('new_string') or ''}"
    if "edits" in tool_input:
        return "\n---\n".join(e.get("new_string", "") for e in tool_input.get("edits") or [])
    return tool_input.get("new_source") or ""


def decide(permission, reason):
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": permission,
                                 "permissionDecisionReason": reason}})


def on_edit(data, cfg_path, cfg):
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        sys.exit(0)
    real = os.path.realpath(file_path)
    root = os.path.realpath(cfg["checkout_root"])
    if not real.startswith(root + os.sep):
        sys.exit(0)                                   # outside the gated checkout: not plan work
    if real == os.path.realpath(cfg["plan_path"]):
        sys.exit(0)                                   # the plan's own progress log stays writable
    locked = common.locked_gates(cfg)
    if not locked:
        sys.exit(0)

    rel = os.path.relpath(real, root)
    excerpt = "" if SECRET_FILE.search(rel) else change_text(tool_input)[:EXCERPT]
    criteria = {g["id"]: f"{g['title']}: {g['work']}" for g in cfg["gates"]}
    criteria["not_plan_work"] = "Not part of this plan: unrelated fixes, tooling, notes, or files no plan step covers."
    question = {"step": {
        "type": "choice",
        "instructions": ("An AI coding agent is carrying out a written plan and is about to make the file change in "
                         "the state. Which plan step does this change belong to?"),
        "criteria": criteria,
    }}
    state = {"file": rel, "tool": data.get("tool_name"), "change_excerpt": excerpt}
    try:
        out = common.ask_jev(cfg, state, question)
        probs = out["answers"]["step"].get("probabilities") or {}
    except Exception as e:
        common.log_event(cfg_path, {"event": "edit_error", "file": rel, "error": str(e)})
        decide("ask", f"Plan gate could not classify this edit (Jev unavailable: {e}). Approve only if it is "
                      f"allowed at the current checkpoint.")

    locked_ids = {g["id"] for g in locked}
    p_locked = sum(p for gid, p in probs.items() if gid in locked_ids)
    top = max(locked_ids, key=lambda gid: probs.get(gid, 0))
    common.log_event(cfg_path, {"event": "edit", "file": rel, "probs": probs, "p_locked": round(p_locked, 3)})
    title = next(g["title"] for g in cfg["gates"] if g["id"] == top)
    if p_locked >= DENY_AT:
        decide("deny", f"Plan gate: this edit to {rel} looks like '{title}' (p={p_locked:.2f}), which the user has "
                       f"not approved yet. Stop and ask the user. They can type 'unlock {top}'.")
    if p_locked >= ASK_AT:
        decide("ask", f"Plan gate: this edit to {rel} may belong to '{title}' (p={p_locked:.2f}), which is still "
                      f"locked. Allow only if it is not that step's work.")
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    cfg_path, cfg = common.find_config(data.get("cwd") or os.getcwd())
    if not cfg:
        sys.exit(0)
    event = data.get("hook_event_name")
    if event == "UserPromptSubmit":
        on_prompt(data, cfg_path, cfg)
    elif event == "PreToolUse":
        on_edit(data, cfg_path, cfg)
    sys.exit(0)


if __name__ == "__main__":
    main()
