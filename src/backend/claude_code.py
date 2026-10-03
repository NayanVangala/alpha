"""Driving Claude Code from rein: what its hooks ask the wearer, and what goes back to Claude.

Claude Code POSTs each hook event to the board server's /api/hooks (an HTTP hook), which answers with these
functions. Get the hooks into Claude Code either way:
- the rein plugin, for every project in the terminal and VS Code alike:
      /plugin marketplace add ~/dublinhacx      then      /plugin install rein@rein
- or one project only (adds to <project>/.claude/settings.local.json):
      uv run python -m src.backend.claude_code install /path/to/project

The hooks:
- SessionStart: asks Claude to end each reply with its guesses for the next step, which lead the cards.
- PreToolUse: the brake. While the wearer's eyes are closed, Claude's next tool call is refused and it stops.
- PermissionRequest: "Claude wants to run npm test" shows on the board as Allow / Deny cards.
- Stop: when Claude finishes a turn, the board offers what to do next; the pick becomes its next instruction.

They only act while rein's floating window is open. If rein isn't running, nothing is connected, the
wearer goes back, or nobody answers, each hook steps aside and Claude Code carries on as usual.
"""

import json
import os
import re
import sys
from pathlib import Path

HOOK_URL = "http://127.0.0.1:8000/api/hooks"
TIMEOUT_S = 600  # how long Claude Code lets a hook that waits for the wearer run
WAIT_S = TIMEOUT_S - 10  # the board gives up just before Claude Code would
# commands that can destroy work, change git history or reach outside the project: Deny is lit first for
# these, and the autopilot never runs them by itself
RISKY = re.compile(
    r"(^|[\s;&|(])(rm|sudo|curl|wget|chmod|chown|dd|mkfs|kill"
    r"|git\s+(push|reset|clean|commit|add|checkout|switch|merge|rebase|stash|tag|branch\s+-[dD]))\b"
)
# Playwright MCP tools (the sandboxed browser): seeing the page needs no answer; acting on it shows a card
BROWSER = re.compile(r"^mcp__(?:plugin_playwright_)?playwright__browser_(\w+)$")
LOOK_ONLY = {"snapshot", "take_screenshot", "wait_for", "tabs", "console_messages", "network_requests", "resize", "close"}
# Default-deny: only these auto-run on silence. Anything else on a command line, any lookup that reaches the web, any
# private file and anything outside the project waits for a bite. Every segment of a command must be on the list.
SAFE_SEGMENT = re.compile(
    r"^(?:(?:ls|pwd|cat|head|tail|wc|grep|rg|echo|which|date|diff|sort|uniq|tree|stat|file|du|basename|dirname|cd|true)(?:\s|$)"
    r"|git\s+(?:status|diff|log|show|rev-parse|ls-files|blame)(?:\s|$)"
    r"|git\s+branch\s*(?:-[avr]+\s*)?$"
    r"|(?:uv\s+run\s+)?(?:python3?\s+-m\s+)?pytest(?:\s|$)"
    r"|(?:uv\s+run\s+)?python3?\s+-m\s+(?:pytest|py_compile)(?:\s|$)"
    r"|npm\s+(?:test|t|run\s+(?:test|build|lint|check|typecheck))(?:\s|$)"
    r"|npx\s+tsc(?:\s|$)|node\s+--check(?:\s|$)|ruff\s+check(?:\s|$))"
)
# $(...), backticks, and redirects to a file can hide or write anything (2>&1 and >/dev/null are fine)
UNSAFE_SHELL = re.compile(r"\$\(|`|(?<![\d&])>(?!&\d|\s*/dev/null)|>>")
SECRET = re.compile(
    r"(\.env\b|\.ssh\b|\.aws\b|\.gnupg\b|\.netrc|\.npmrc|\.pem\b|\.key\b|id_(?:rsa|ed25519)|credentials|secrets?\b|keychain)", re.I
)
PROTECTED = re.compile(r"(^|/)(\.claude/|\.git/|hooks\.json$)")  # an agent must not be able to switch rein's hooks off


def bash_is_safe(cmd):
    if UNSAFE_SHELL.search(cmd):
        return False
    segments = [seg.strip() for seg in re.split(r"&&|\|\||;|\||\n", cmd) if seg.strip()]
    return bool(segments) and all(SAFE_SEGMENT.match(seg) for seg in segments)


def private_or_outside(path, cwd):
    """A secret, a hook or config file, or a path outside the project: these need a bite, even to read."""
    if SECRET.search(path) or PROTECTED.search(path):
        return True
    return bool(cwd) and path.startswith("/") and not path.startswith(cwd.rstrip("/") + "/")


NEXT_LINE = re.compile(r"^[\s*_`]*Next[\s*_`]*:\s*(.+?)\s*$", re.M | re.I)
DONE = "I'm done"
FIXED_NEXT = {"Keep going": "going", "Run the tests": "test"}  # always offered, unless a guess already says it
GUIDE = (
    "The user is driving this session hands-free with rein, a board they control by biting down and closing their eyes, "
    "so they can't type. End every reply with one line: `Next: <step> | <step> | <step>`, the three instructions "
    "about this project they are most likely to give you next, like `Run the tests` or `Commit this`. "
    "Write each one out in full, 2 to 6 words."
)
NO = (
    "The user said no on rein, their hands-free board. That's their choice, not an error: don't retry it or try "
    "to get around it. End your turn with one line on what you'd do instead."
)
BRAKED = (
    "The user closed their eyes to stop you (rein's brake). Don't call any more tools. "
    "End your turn now with one line on where you stopped."
)


def lines(text):
    return len(str(text or "").splitlines())


def describe(tool, inp, cwd=""):
    """(title, detail, risky) for a permission card."""
    if tool == "Bash":
        cmd = " ".join(str(inp.get("command", "")).split())
        return "Claude wants to run", cmd, bool(RISKY.search(cmd)) or not bash_is_safe(cmd) or bool(SECRET.search(cmd))
    if tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        risky = private_or_outside(path, cwd)
        if cwd and path.startswith(cwd.rstrip("/") + "/"):
            path = os.path.relpath(path, cwd)
        if tool == "Write":
            return "Claude wants to write", f"{path} ({lines(inp.get('content'))} lines)", risky
        edits = inp.get("edits") or [inp]
        added = sum(lines(e.get("new_string")) for e in edits)
        removed = sum(lines(e.get("old_string")) for e in edits)
        return "Claude wants to edit", f"{path} (+{added} −{removed})", risky
    if tool in ("Read", "Glob", "Grep", "LS"):
        what = str(inp.get("file_path") or inp.get("pattern") or inp.get("path") or "")
        risky = private_or_outside(what, cwd)
        if cwd and what.startswith(cwd.rstrip("/") + "/"):
            what = os.path.relpath(what, cwd)
        return "Claude wants to read", what, risky
    if m := BROWSER.match(tool):
        what, element = m.group(1), str(inp.get("element") or "")
        if what == "navigate":
            return "Claude wants to open", str(inp.get("url") or ""), True  # a new site is a lookup: it waits for a bite
        if what in ("navigate_back", "hover"):
            return "Claude wants to " + ("go back" if what == "navigate_back" else "point at"), element, False
        if what == "click":
            return "Claude wants to click", element or "something on the page", False
        if what == "type":
            return "Claude wants to type", f'"{clip(str(inp.get("text") or ""), 60)}"' + (f" into {element}" if element else ""), False
        if what == "fill_form":
            return "Claude wants to fill in a form", f"{len(inp.get('fields') or [])} fields", False
        if what == "press_key":
            return "Claude wants to press", str(inp.get("key") or ""), False
        if what == "select_option":
            return "Claude wants to choose", element or "an option", False
        if what in LOOK_ONLY:
            return "Claude wants to look at the page", "", False
        return f"Claude wants to {what.replace('_', ' ')} in the browser", json.dumps(inp)[:200], True  # scripts, uploads: Deny first
    if tool in ("WebFetch", "WebSearch"):
        return "Claude wants to look up", str(inp.get("url") or inp.get("query") or ""), True
    return f"Claude wants to use {tool}", json.dumps(inp)[:200], True  # anything unknown: Deny lit first


def next_steps(message):
    """(Claude's guesses for the next instruction, its reply without the Next line)."""
    found = NEXT_LINE.findall(message or "")
    guesses = [g.strip(" `*_.") for g in found[-1].split("|")] if found else []
    summary = " ".join(NEXT_LINE.sub("", message or "").split())
    return [g for g in guesses if 1 < len(g) <= 60][:3], summary


def clip(text, n):
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


# Each handler returns the JSON Claude Code expects, or None for "no decision" (Claude Code asks as usual).
# ask(kind, title, detail, options, auto) puts a question on the board and returns the pick, or None.


def on_permission(event, ask):
    if (m := BROWSER.match(event.get("tool_name", ""))) and m.group(1) in LOOK_ONLY:
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
    title, detail, risky = describe(event.get("tool_name", ""), event.get("tool_input") or {}, event.get("cwd", ""))
    picked = ask("permission", title, detail, ["Deny", "Allow"] if risky else ["Allow", "Deny"], auto=not risky)
    if picked is None:
        return None
    decision = {"behavior": "allow"} if picked == "Allow" else {"behavior": "deny", "message": NO}
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def on_stop(event, ask):
    guesses, summary = next_steps(event.get("last_assistant_message", ""))
    fixed = [f for f, word in FIXED_NEXT.items() if not any(word in g.lower() for g in guesses)]
    options = [o for o in dict.fromkeys([*guesses, *fixed]) if o != DONE][:5] + [DONE]
    picked = ask("next", "Claude finished", clip(summary, 280), options, auto=bool(guesses))
    if picked in (None, DONE):
        return None  # let Claude stop
    return {
        "decision": "block",
        "reason": f'The user picked their next instruction on rein, their hands-free board: "{picked}". Do that now.',
    }


def on_pre_tool(event, braked):
    if not braked():
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": BRAKED}}


def on_session_start(event):
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": GUIDE}}


def hooks_config(url=HOOK_URL):
    """The hooks block for Claude Code settings (and the plugin's hooks.json): every event goes to rein."""
    def hook(timeout):
        return [{"hooks": [{"type": "http", "url": url, "timeout": timeout}]}]

    # SessionStart's added context only reaches Claude from a command hook, so this one forwards with curl
    # (on every Mac and on Windows 10+); "|| true" keeps rein being off from showing up as a hook error
    forward = f"curl -s --max-time 4 -H 'Content-Type: application/json' --data-binary @- {url} || true"
    return {
        "SessionStart": [{"hooks": [{"type": "command", "command": forward, "timeout": 5}]}],
        "PreToolUse": hook(5),  # the brake runs before every tool call, so it must answer fast
        "PermissionRequest": hook(TIMEOUT_S),  # these two wait for the wearer
        "Stop": hook(TIMEOUT_S),
    }


def install(project):
    """Add rein's hooks to one project's local Claude Code settings, keeping anything else there."""
    settings = Path(project).expanduser().resolve() / ".claude" / "settings.local.json"
    data = json.loads(settings.read_text()) if settings.exists() else {}
    hooks = data.setdefault("hooks", {})
    mine = lambda entry: any(h.get("url") == HOOK_URL or HOOK_URL in h.get("command", "")  # noqa: E731
                             or "claude_code.py" in h.get("command", "") for h in entry.get("hooks", []))
    for event, entries in hooks_config().items():
        hooks[event] = [e for e in hooks.get(event, []) if not mine(e)] + entries
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n")
    return settings


if __name__ == "__main__":
    if sys.argv[1:2] != ["install"]:
        sys.exit("usage: python -m src.backend.claude_code install /path/to/project")
    print(f"rein's hooks are in {install(sys.argv[2] if len(sys.argv) > 2 else '.')}")
