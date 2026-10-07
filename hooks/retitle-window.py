#!/usr/bin/env python3
"""
Auto-retitle the terminal tab (Ghostty via OSC 2; Apple Terminal via AppleScript only when running in it).

Why: Claude Code computes `aiTitle` ONCE from the first prompt and never
refreshes it, so native titles go stale and describe the session's ORIGINAL
topic. This Stop hook regenerates a clean, short title from the recent
conversation every turn.

Title source: a fast model (Haiku) via the local `claude` CLI in headless
print mode, using the existing Max/OAuth login (no API key needed). It is
invoked with `--setting-sources project` so THIS hook does not load in the
subprocess (no recursion) and `--strict-mcp-config` so no MCP servers spin up.
Falls back to a cleaned latest-prompt heuristic if the model call fails.

Non-blocking: the hook captures its tty, then double-forks and returns
immediately so the turn never waits on the ~5-7s model call. The detached
child writes the OSC title sequence to the captured tty device.
"""
import sys, json, re, os, shutil, subprocess

CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
MODEL = "claude-haiku-4-5"
MAXLEN = 46
LLM_TIMEOUT = 30

ACK = (
    "yes","no","ok","okay","sure","yep","yeah","yup","y","k","kk","nah",
    "do","it","go","ahead","proceed","continue","cont","thanks","thank","you",
    "ty","please","pls","perfect","great","nice","cool","good","awesome",
    "sounds","lgtm","ship","lets","let's","hey","also","and","so","now",
)

# Prefix every window title with a short tag so you can tell projects apart at a
# glance. Add a row per project you work in; the cwd substring is matched first,
# then the WORK_ACCOUNT env var as a fallback for unlinked directories.
PROJECT_TAGS = {
    # "acme": "AC",       # cwd contains "acme" -> "AC · <title>"
    # "side-project": "SP",
}

def client_tag(cwd: str) -> str:
    c = (cwd or "").lower()
    for needle, tag in PROJECT_TAGS.items():
        if needle in c:
            return tag
    wa = (os.environ.get("WORK_ACCOUNT") or "").lower()
    return PROJECT_TAGS.get(wa, "")

def msg_text(m) -> str:
    """Extract plain text from a transcript message's content."""
    if isinstance(m, str):
        return m
    if isinstance(m, list):
        parts = []
        for b in m:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif isinstance(b, str):
                parts.append(b)
        return " ".join(parts)
    return ""

def gather(tpath):
    """Return (recent_user_prompts[list], last_assistant_text, ai_title)."""
    prompts, assistants, ai_title = [], [], None
    with open(tpath) as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            if t == "last-prompt":
                p = (o.get("lastPrompt") or "").strip()
                if p:
                    prompts.append(p)
            elif t == "ai-title":
                ai_title = o.get("aiTitle") or ai_title
            elif t == "assistant":
                txt = msg_text((o.get("message") or {}).get("content"))
                txt = re.sub(r"\s+", " ", txt).strip()
                if txt:
                    assistants.append(txt)
    return prompts, (assistants[-1] if assistants else ""), ai_title

# ---- heuristic fallback ----
def substantive(text):
    w = re.findall(r"[A-Za-z0-9'#/.-]+", text)
    i = 0
    while i < len(w) and w[i].lower().strip(",.!?") in ACK:
        i += 1
    return len(w) - i >= 3

def clean_phrase(text):
    words = text.split()
    while words and re.sub(r"[,.!?]", "", words[0].lower()) in ACK:
        words.pop(0)
    s = " ".join(words) if words else text.strip()
    s = re.sub(r"\s+", " ", s).strip().strip("-–—:· ")
    if not s:
        return s
    s = s[0].upper() + s[1:]
    if len(s) > MAXLEN:
        s = s[:MAXLEN - 1].rstrip() + "…"
    return s

def heuristic_title(prompts, ai_title):
    for p in reversed(prompts):
        if substantive(p):
            return clean_phrase(p)
    if prompts:
        return clean_phrase(prompts[-1])
    return (ai_title or "Claude").strip()

# ---- LLM title ----
def llm_title(prompts, last_assistant, cwd):
    recent = prompts[-5:]
    ctx = ""
    for p in recent:
        ctx += f"\nUSER: {p[:280]}"
    if last_assistant:
        ctx += f"\nASSISTANT (latest): {last_assistant[:500]}"
    prompt = (
        "You are naming a terminal tab for a software/marketing work session. "
        "From the recent conversation below, write a TAB TITLE of AT MOST 5 words "
        "that names the CURRENT task or topic. Use concrete nouns, no filler, "
        "no quotes, no trailing punctuation, fix any obvious typos. "
        "Output ONLY the title.\n"
        f"\nWorking dir: {cwd}\nConversation:{ctx}\n\nTitle:"
    )
    env = dict(os.environ)
    env["CC_RETITLE_ACTIVE"] = "1"  # extra recursion guard
    try:
        out = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", MODEL,
             "--setting-sources", "project",
             "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}'],
            cwd="/tmp", env=env, capture_output=True, text=True,
            timeout=LLM_TIMEOUT,
        )
    except Exception:
        return None
    title = (out.stdout or "").strip().strip('"').strip("'").splitlines()
    title = title[0].strip() if title else ""
    title = re.sub(r"\s+", " ", title).strip(" .…-–—:·")
    # reject junk (errors, refusals, over-long)
    if not title or len(title) > MAXLEN or title.lower().startswith(("error", "i ", "i'm", "sorry")):
        return None
    return title[0].upper() + title[1:]

def find_tty():
    """Walk up the process tree to find the controlling terminal device.
    Hooks run without /dev/tty, but an ancestor (the claude process) has one."""
    pid = os.getpid()
    for _ in range(8):
        try:
            r = subprocess.run(["ps", "-o", "tty=,ppid=", "-p", str(pid)],
                               capture_output=True, text=True)
            fields = r.stdout.split()
            if not fields:
                return None
            tt, ppid = fields[0], (fields[1] if len(fields) > 1 else "")
            if tt.startswith("ttys"):
                return "/dev/" + tt
            if ppid in ("", "0", "1"):
                return None
            pid = int(ppid)
        except Exception:
            return None
    return None

def write_title(ttydev, label):
    """Set the tab title for ttydev.

    Ghostty/iTerm2/etc: OSC 2 written straight to the tty. Apple Terminal only
    when we're actually running in it -- `tell application "Terminal"` launches
    Terminal.app if it isn't open, so never reach it from another emulator."""
    if os.environ.get("TERM_PROGRAM") != "Apple_Terminal":
        safe = re.sub(r"[\x00-\x1f\x7f]", "", label)
        try:
            with open(ttydev, "w") as f:
                f.write(f"\033]2;{safe}\007")
        except Exception:
            pass
        return
    script = (
        'on run argv\n'
        'set theTty to item 1 of argv\n'
        'set theTitle to item 2 of argv\n'
        'tell application "Terminal"\n'
        '  repeat with w in windows\n'
        '    repeat with t in tabs of w\n'
        '      try\n'
        '        if tty of t is theTty then set custom title of t to theTitle\n'
        '      end try\n'
        '    end repeat\n'
        '  end repeat\n'
        'end tell\n'
        'end run\n'
    )
    try:
        subprocess.run(["osascript", "-e", script, ttydev, label],
                       capture_output=True, text=True, timeout=10)
    except Exception:
        pass

def main():
    if os.environ.get("CC_RETITLE_ACTIVE"):
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tpath = data.get("transcript_path")
    cwd = data.get("cwd") or os.getcwd()
    if not tpath or not os.path.exists(tpath):
        return
    sid = data.get("session_id") or ""
    prompt_mode = bool(sid) and os.path.exists(
        os.path.expanduser(f"~/.claude/state/prompt-mode/{sid}"))

    # find our controlling terminal device BEFORE detaching (parent chain has it)
    ttydev = find_tty()
    if not ttydev:
        return

    # detach: double-fork so the turn doesn't wait on the model call
    try:
        if os.fork() > 0:
            return
    except Exception:
        # can't fork; just do it inline (rare)
        run(tpath, cwd, ttydev, prompt_mode)
        return
    os.setsid()
    try:
        if os.fork() > 0:
            os._exit(0)
    except Exception:
        pass
    # grandchild: detached worker
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0); os.dup2(devnull, 1); os.dup2(devnull, 2)
    run(tpath, cwd, ttydev, prompt_mode)
    os._exit(0)

def run(tpath, cwd, ttydev, prompt_mode=False):
    try:
        prompts, last_assistant, ai_title = gather(tpath)
        title = llm_title(prompts, last_assistant, cwd) or heuristic_title(prompts, ai_title)
        tag = client_tag(cwd)
        label = f"{tag} · {title}" if tag else title
        if prompt_mode:
            label = f"✎ PROMPT · {label}"
        write_title(ttydev, label)
    except Exception:
        pass

if __name__ == "__main__":
    main()
