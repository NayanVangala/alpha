from src.backend.history import HALF_LIFE_DAYS, LOOKBACK_DAYS, TOP, open_history, record, suggestions

DAY = 86400
NOW = 1_790_000_000.0  # a fixed moment; hours are compared in local time on both sides


def labels(db, now=NOW):
    return [s["label"] for s in suggestions(db, now=now)]


def test_recent_and_frequent_first(tmp_path):
    db = open_history(tmp_path / "h.db")
    record(db, "Old news.", now=NOW - 4 * HALF_LIFE_DAYS * DAY)
    for _ in range(3):
        record(db, "Water, please.", now=NOW - DAY + 5 * 3600)
    record(db, "Yes.", now=NOW - DAY + 5 * 3600)
    assert labels(db) == ["Water, please.", "Yes.", "Old news."]


def test_same_time_of_day_wins_a_tie(tmp_path):
    db = open_history(tmp_path / "h.db")
    record(db, "Other hour.", now=NOW - DAY + 6 * 3600)  # a little more recent, but at another hour
    record(db, "Same hour.", now=NOW - DAY)
    assert labels(db) == ["Same hour.", "Other hour."]


def test_old_uses_drop_out_and_the_list_is_short(tmp_path):
    db = open_history(tmp_path / "h.db")
    record(db, "Last month.", now=NOW - (LOOKBACK_DAYS + 1) * DAY)
    for i in range(TOP + 2):
        record(db, f"Phrase {i}.", now=NOW - i * 3600)
    got = labels(db)
    assert len(got) == TOP and "Last month." not in got


def test_texts_and_calls_keep_their_recipient(tmp_path):
    db = open_history(tmp_path / "h.db")
    record(db, "Please come here.", "text", "Mom", now=NOW - 60)
    record(db, "Please come, I need you.", "call", "Nurse", now=NOW - 120)
    record(db, "Thank you.", now=NOW - 180)
    assert suggestions(db, now=NOW) == [
        {"label": "Text Mom: Please come here.", "phrase": "Please come here.", "exact": True, "action": "text", "to": "Mom"},
        {"label": "Call Nurse: Please come, I need you.", "phrase": "Please come, I need you.", "exact": True,
         "action": "call", "to": "Nurse"},
        {"label": "Thank you.", "phrase": "Thank you.", "exact": True},
    ]
