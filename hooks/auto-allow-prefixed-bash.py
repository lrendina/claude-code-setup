#!/usr/bin/env python3
"""
Auto-allow read-only bash commands prefixed by harmless env-var assignments.

Without this hook, Claude Code's `Bash(vercel ls:*)` allowlist won't match
`WORK_ACCOUNT=acme vercel ls` because the prefix breaks the pattern.
This hook strips known-harmless prefixes (WORK_ACCOUNT=, VD_BYPASS=, etc.)
and auto-allows if the stripped form is a known read-only command.
"""
import json
import re
import sys

HARMLESS_PREFIX_RE = re.compile(
    r'^(?:'
    r'WORK_ACCOUNT=[A-Za-z0-9_-]+\s+'
    r'|VD_BYPASS=1\s+'
    r'|GH_BYPASS=1\s+'
    r'|NEXT_TELEMETRY_DISABLED=1\s+'
    r'|CI=1\s+'
    r')+'
)

SAFE_STRIPPED = [
    re.compile(r'^vercel ls(?:\s|$)'),
    re.compile(r'^vercel logs(?:\s|$)'),
    re.compile(r'^vercel inspect(?:\s|$)'),
    re.compile(r'^vercel whoami(?:\s|$)'),
    re.compile(r'^vercel env ls(?:\s|$)'),
    re.compile(r'^vercel projects(?:\s|$)'),
    re.compile(r'^vercel domains ls(?:\s|$)'),
    re.compile(r'^vercel teams ls(?:\s|$)'),
    re.compile(r'^gh auth status(?:\s|$)'),
    re.compile(r'^gh pr (?:view|list|diff|checks|status)(?:\s|$)'),
    re.compile(r'^gh repo view(?:\s|$)'),
    re.compile(r'^gh issue (?:view|list|status)(?:\s|$)'),
    re.compile(r'^gh run (?:view|list)(?:\s|$)'),
    re.compile(r'^git (?:status|log|diff|show|branch|remote|stash list|reflog|blame|config --get)(?:\s|$)'),
    re.compile(r'^bunx tsc(?:\s|$)'),
    re.compile(r'^bun x tsc(?:\s|$)'),
    re.compile(r'^npx tsc(?:\s|$)'),
    re.compile(r'^pnpm exec tsc(?:\s|$)'),
    re.compile(r'^railway logs(?:\s|$)'),
    re.compile(r'^railway list(?:\s|$)'),
    re.compile(r'^railway status(?:\s|$)'),
    re.compile(r'^fly logs(?:\s|$)'),
    re.compile(r'^fly status(?:\s|$)'),
    re.compile(r'^flyctl logs(?:\s|$)'),
    re.compile(r'^flyctl status(?:\s|$)'),
    re.compile(r'^flyctl machine list(?:\s|$)'),
]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get('tool_name') != 'Bash':
        sys.exit(0)

    cmd = payload.get('tool_input', {}).get('command', '').strip()
    if not cmd:
        sys.exit(0)

    stripped = HARMLESS_PREFIX_RE.sub('', cmd).strip()
    if stripped == cmd:
        sys.exit(0)  # no prefix, let normal flow handle

    for pat in SAFE_STRIPPED:
        if pat.match(stripped):
            print(json.dumps({
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'allow',
                    'permissionDecisionReason': f'auto-allow: env-var prefix stripped, base is read-only ({stripped[:60]})'
                }
            }))
            sys.exit(0)

    sys.exit(0)


if __name__ == '__main__':
    main()
