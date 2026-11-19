#!/usr/bin/env python3
"""PreToolUse hook: the agent may run only these git commands, nothing else.

Runs before the permission check, also in bypass mode. Exit 2 blocks the call.
"""
import json
import re
import sys

FILES = r"(?:SOUL\.md|CLAUDE\.md)(?: (?:SOUL\.md|CLAUDE\.md))?"
ALLOWED = [
    r"git status(?: --short)?",
    rf"git diff(?: --stat)?(?: -- {FILES})?",
    r"git log --oneline(?: -\d{1,3})?",
    # One-line message in double quotes, no $ ` \ " inside; commits only these files.
    rf'git commit -m "[^"$`\\\n]{{1,200}}" -- {FILES}',
]

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    cmd = ""
if any(re.fullmatch(p, cmd.strip()) for p in ALLOWED):
    sys.exit(0)
print(
    "Blocked by the workspace hook. Allowed shell commands: git status, git diff [-- SOUL.md CLAUDE.md], "
    'git log --oneline [-N], git commit -m "<message>" -- SOUL.md [CLAUDE.md]. Nothing else.',
    file=sys.stderr,
)
sys.exit(2)
