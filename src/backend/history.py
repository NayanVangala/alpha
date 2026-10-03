"""What the wearer said or sent, so the Suggested tile can offer it again in fewer clenches."""

import sqlite3
import time
from pathlib import Path

DB = Path("data/board.db")  # gitignored with the rest of data/
HALF_LIFE_DAYS = 3  # a use counts half as much three days later
SAME_HOUR_BOOST = 1.5  # said within an hour of this time of day before: probably a routine
LOOKBACK_DAYS = 30
TOP = 5


def open_history(path=DB):
    path.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute("CREATE TABLE IF NOT EXISTS said (ts REAL, sentence TEXT, action TEXT, recipient TEXT)")
    return db


def record(db, sentence, action="speak", to=None, now=None):
    db.execute("INSERT INTO said VALUES (?,?,?,?)", (time.time() if now is None else now, sentence, action, to))
    db.commit()


def suggestions(db, now=None, top=TOP):
    """Up to `top` board tiles, most likely first. Each is a finished sentence that goes straight to confirm."""
    now = time.time() if now is None else now
    hour = time.localtime(now).tm_hour
    scores = {}
    for ts, sentence, action, to in db.execute(
        "SELECT ts, sentence, action, recipient FROM said WHERE ts > ?", (now - LOOKBACK_DAYS * 86400,)
    ):
        weight = 0.5 ** ((now - ts) / 86400 / HALF_LIFE_DAYS)
        gap = abs(time.localtime(ts).tm_hour - hour)
        if min(gap, 24 - gap) <= 1:
            weight *= SAME_HOUR_BOOST
        scores[sentence, action, to] = scores.get((sentence, action, to), 0.0) + weight
    ranked = sorted(scores, key=scores.get, reverse=True)[:top]
    return [
        {"label": s if a == "speak" else to if a == "routine" else f"{'Text' if a == 'text' else 'Call'} {to}: {s}",
         "phrase": s, "exact": True, **({} if a == "speak" else {"action": a, "to": to})}
        for s, a, to in ranked
    ]
