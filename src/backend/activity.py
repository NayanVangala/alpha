"""What's on screen right now (macOS), and notification banners. No permissions needed."""

import re
import subprocess


def frontmost_app():
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=1).stdout.strip()
        out = subprocess.run(
            ["lsappinfo", "info", "-only", "name", asn], capture_output=True, text=True, timeout=1
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    m = re.search(r'"LSDisplayName"="(.*)"', out)
    return m.group(1) if m else "unknown"


def notify(title, message):
    """macOS notification banner with a soft sound. Fire-and-forget, so a slow osascript can't stall the loop."""
    script = f'display notification {_q(message)} with title {_q(title)} sound name "Tink"'
    try:
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
