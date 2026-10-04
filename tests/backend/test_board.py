import json

import pytest

from src.backend.board import (
    GATE_BITE_S,
    AUTO_S,
    BACK_S,
    FINDING_S,
    HELP_S,
    HELP_TEXT,
    MAX_TILES,
    PICK_PAUSE_S,
    QUICK_REPLIES,
    TALK_S,
    Board,
    load_menu,
)

MENU = {"label": "Home", "children": [
    {"label": "I need", "children": [
        {"label": "Water", "phrase": "Water, please."},
        {"label": "Pain", "children": [{"label": "A lot", "phrase": "It hurts a lot."}]},
    ]},
    {"label": "Yes", "phrase": "Yes."},
]}


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def board_at(clock, **kw):
    board = Board(MENU, clock=clock, **kw)
    board.clock_ = clock
    return board


@pytest.fixture
def b():
    return board_at(Clock())


@pytest.fixture
def scan():
    """The fallback: the highlight steps on its own."""
    return board_at(Clock(), scan_s=1.0)


def at(board, seconds):
    """Move time `seconds` past the current screen's start."""
    board.clock_.t = board.scan_from - PICK_PAUSE_S + seconds


def test_glances_move_the_highlight_and_wrap(b):
    assert b.state()["lit"] == 0 and b.state()["mode"] == "glance" and b.state()["next_s"] is None
    b.clock_.t += 30
    assert b.state()["lit"] == 0  # nothing moves on its own
    b.handle("glance_right")
    assert b.state()["lit"] == 1
    b.handle("glance_right")
    assert b.state()["lit"] == 0  # two cards: wraps
    b.handle("glance_left")
    b.handle("clench")
    assert b.state()["sentence"] == "Yes."
    b.handle("clench")
    assert b.state()["took"]["glances"] == 3 and b.state()["took"]["n"] == 2


def test_clench_picks_the_card_lit_when_it_began(b):
    b.clock_.t += 1
    b.handle("glance_right")  # slipped in while the jaw was already closing
    b.clock_.t += 0.3
    b.handle("clench", ago=0.6)
    assert b.state()["path"] == ["I need"]


def test_glances_do_nothing_on_a_sentence_or_under_go_back(b):
    b.handle("clench")
    b.handle("glance_right")  # Pain
    b.handle("double_blink")
    b.handle("glance_left")  # under "Go back?": ignored
    b.clock_.t += BACK_S  # stay
    assert b.state()["lit"] == 1 and b.state()["overlay"] is None  # the highlight stayed put
    b.handle("glance_left")
    b.handle("clench")  # Water: confirm screen
    b.handle("glance_right")
    assert b.state()["sentence"] == "Water, please."


def test_scan_fallback_holds_first_tile_then_steps_and_wraps(scan):
    at(scan, 0)
    assert scan.state()["lit"] == 0 and scan.state()["mode"] == "scan"
    at(scan, PICK_PAUSE_S + 0.99)
    assert scan.state()["lit"] == 0
    at(scan, PICK_PAUSE_S + 1.0)
    assert scan.state()["lit"] == 1
    scan.handle("glance_left")  # glances don't steer the scan
    assert scan.state()["lit"] == 1
    at(scan, PICK_PAUSE_S + 2.0)
    assert scan.state()["lit"] == 0  # two tiles: wraps


def test_pick_menu_then_leaf_then_confirm_says_it(b):
    b.handle("clench")  # "I need"
    assert b.state()["path"] == ["I need"]
    b.handle("clench")  # "Water"
    s = b.state()
    assert s["screen"] == "confirm" and s["sentence"] == "Water, please." and s["said"] is None
    b.handle("clench")
    s = b.state()
    assert s["said"]["text"] == "Water, please." and s["path"] == [] and s["screen"] == "menu"


def test_scan_clench_picks_the_tile_lit_when_it_began(scan):
    at(scan, PICK_PAUSE_S + 1.1)  # "Yes" is lit now
    scan.handle("clench", ago=0.3)  # but the jaw started closing while "I need" was lit
    assert scan.state()["path"] == ["I need"]


def test_scan_clench_on_the_current_tile(scan):
    at(scan, PICK_PAUSE_S + 1.1)
    scan.handle("clench")
    assert scan.state()["sentence"] == "Yes."


def test_go_back_needs_a_clench_to_confirm(b):
    b.handle("clench")
    b.handle("double_blink")
    assert b.state()["overlay"] == "back"
    b.handle("clench")
    assert b.state()["path"] == [] and b.state()["overlay"] is None


def test_go_back_times_out_to_stay(b):
    b.handle("clench")
    b.handle("double_blink")
    b.clock_.t += BACK_S
    assert b.state()["overlay"] is None and b.state()["path"] == ["I need"]


def test_back_from_a_sentence_returns_to_its_tiles_unsaid(b):
    b.handle("clench")
    b.handle("clench")  # Water: confirm screen
    b.handle("double_blink")
    b.handle("clench")
    s = b.state()
    assert s["screen"] == "menu" and s["path"] == ["I need"] and s["sentence"] is None and s["said"] is None


def test_double_blink_at_home_does_nothing(b):
    b.handle("double_blink")
    assert b.state()["overlay"] is None


def test_help_countdown_runs_out_to_the_alert(b):
    b.handle("clench")
    b.handle("long_clench")
    assert b.state()["overlay"] == "help" and b.state()["left_s"] == HELP_S
    b.handle("clench")  # a clench doesn't stop it
    b.clock_.t += HELP_S
    s = b.state()
    assert s["alert"]["text"] == HELP_TEXT and s["overlay"] is None and s["path"] == []


def test_double_blink_cancels_help(b):
    b.handle("long_clench")
    b.handle("double_blink")
    b.clock_.t += HELP_S
    assert b.state()["alert"] is None


def test_help_opens_over_a_sentence_and_over_go_back(b):
    b.handle("clench")
    b.handle("clench")
    b.handle("double_blink")
    b.handle("long_clench")
    assert b.state()["overlay"] == "help"


def test_each_output_gets_a_new_id(b):
    for _ in range(2):
        b.handle("clench")
        b.handle("clench")
        b.handle("clench")
    first = b.state()["said"]["id"]
    b.handle("long_clench")
    b.clock_.t += HELP_S
    assert b.state()["alert"]["id"] > first


def test_unknown_input_is_refused(b):
    with pytest.raises(ValueError):
        b.handle("wink")


def test_menu_file_checks(tmp_path):
    load_menu(contacts=[{"name": "Mom"}])  # the shipped menu
    for bad in ({"label": "Home", "children": [{"label": "x", "phrase": "x"}] * (MAX_TILES + 1)},
                {"label": "Home", "children": [{"label": "no phrase"}]}):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            load_menu(p)


def test_texts_go_through_confirm_then_act(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"label": "Home", "children": [{"label": "People", "from_contacts": True}]}))
    acts = []
    board = Board(load_menu(p, contacts=[{"name": "Mom"}]), clock=Clock(), act=lambda *a: acts.append(a))
    for _ in range(3):  # People > Mom > Come here
        board.handle("clench")
    s = board.state()
    assert (s["screen"], s["action"], s["to"], acts) == ("confirm", "text", "Mom", [])
    board.handle("clench")
    assert acts == [("text", "Please come here.", "Mom")] and board.state()["said"] is None
    board.notify("Texted Mom")
    assert board.state()["notice"]["text"] == "Texted Mom"


def test_help_calls_out_when_it_runs_out():
    acts, clock = [], Clock()
    board = Board(MENU, clock=clock, act=lambda *a: acts.append(a))
    board.handle("long_clench")
    clock.t += HELP_S
    board.state()
    assert acts == [("help", HELP_TEXT, None)]


def with_ai(clock=None):
    asked = []
    return Board(MENU, clock=clock or Clock(), suggest=lambda *a: asked.append(a)), asked


def test_ai_options_come_before_the_confirm():
    board, asked = with_ai()
    board.handle("clench")
    board.handle("clench")  # I need > Water
    s = board.state()
    assert s["screen"] == "options" and s["finding"] and s["plain"] == "Water, please." and s["path"] == ["I need", "Water"]
    path, phrase, token, recent = asked[0]
    assert (path, phrase, recent) == (["I need", "Water"], "Water, please.", [])
    board.options_ready(token, ["Could I get some water?"])
    s = board.state()
    assert [t["label"] for t in s["tiles"]] == ["Could I get some water?", "Water, please."] and s["lit"] == 0
    assert [t["guess"] for t in s["tiles"]] == [True, False]  # the AI's sentence leads, marked as its guess
    board.handle("clench")  # the AI's sentence
    assert board.state()["sentence"] == "Could I get some water?"
    board.handle("clench")
    assert board.state()["said"]["text"] == "Could I get some water?"
    board.handle("clench")
    board.handle("clench")
    assert asked[1][3] == ["Could I get some water?"]  # what was said goes along as context


def test_clench_while_finding_takes_the_plain_sentence_and_late_answers_are_dropped():
    board, asked = with_ai()
    for _ in range(3):
        board.handle("clench")
    assert board.state()["screen"] == "confirm" and board.state()["sentence"] == "Water, please."
    board.options_ready(asked[0][2], ["Too late."])
    assert board.state()["sentence"] == "Water, please."


def test_no_answer_in_time_falls_back_to_the_plain_sentence():
    clock = Clock()
    board, _ = with_ai(clock)
    board.handle("clench")
    board.handle("clench")
    clock.t += FINDING_S
    assert board.state()["sentence"] == "Water, please."


def test_nothing_extra_from_the_ai_goes_straight_to_confirm():
    board, asked = with_ai()
    board.handle("clench")
    board.handle("clench")
    board.options_ready(asked[0][2], [])
    assert board.state()["screen"] == "confirm"


def test_texts_never_ask_the_ai(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"label": "Home", "children": [{"label": "People", "from_contacts": True}]}))
    asked = []
    board = Board(load_menu(p, contacts=[{"name": "Mom"}]), clock=Clock(), suggest=lambda *a: asked.append(a))
    for _ in range(3):
        board.handle("clench")
    assert board.state()["screen"] == "confirm" and asked == []


def test_guesses_lead_home_and_skip_the_ai():
    saved, asked = [], []
    guess = lambda label: {"label": label, "phrase": label, "exact": True}  # noqa: E731
    board = Board(MENU, clock=Clock(), suggest=lambda *a: asked.append(a), remember=lambda *a: saved.append(a),
                  recall=lambda: [guess(x) for x in ("Water, please.", "Thanks.", "Hi.", "Bye.")])
    tiles = board.state()["tiles"]
    assert [t["label"] for t in tiles] == ["Water, please.", "Thanks.", "Hi.", "I need", "Yes"]  # top 3, then the menu
    assert [t["guess"] for t in tiles] == [True, True, True, False, False] and board.state()["lit"] == 0
    board.handle("clench")  # the best guess
    assert board.state()["screen"] == "confirm" and asked == []  # already a full sentence
    board.handle("clench")
    s = board.state()
    assert saved == [("Water, please.", "speak", None)] and s["took"] == {"id": s["said"]["id"], "n": 2, "glances": 0}


def test_the_full_path_counts_every_clench():
    board = Board(MENU, clock=Clock(), remember=lambda *a: None)
    for _ in range(3):  # I need > Water > confirm
        board.handle("clench")
    board.handle("double_blink")  # opens and dismisses nothing at Home; not a clench
    assert board.state()["took"]["n"] == 3


def test_only_board_output_can_be_voiced(b):
    for _ in range(3):  # I need > Water > confirm
        b.handle("clench")
    said = b.state()["said"]
    assert b.text_of(said["id"]) == "Water, please." and b.text_of(999) is None


def with_replies(clock=None):
    asked = []
    clock = clock or Clock()
    board = Board(MENU, clock=clock, reply=lambda *a: asked.append(a))
    board.clock_ = clock
    return board, asked


def test_what_someone_says_opens_replies_at_home():
    board, asked = with_replies()
    board.heard("Do you want some water?")
    s = board.state()
    assert s["screen"] == "replies" and s["heard"] == "Do you want some water?" and s["thinking"]
    assert [t["label"] for t in s["tiles"]] == list(QUICK_REPLIES)  # usable before the AI answers
    heard, dialog, token = asked[0]
    assert (heard, dialog) == ("Do you want some water?", [("them", "Do you want some water?")])
    board.replies_ready(token, ["Yes, please.", "No."])
    assert [t["label"] for t in board.state()["tiles"]] == ["Yes, please.", "No.", "Yes.", "Can you say that again?"]
    assert [t["guess"] for t in board.state()["tiles"]] == [True, True, False, False]
    board.handle("clench")  # "Yes, please."
    board.handle("clench")  # confirm
    assert board.state()["said"]["text"] == "Yes, please." and board.state()["screen"] == "menu"
    assert list(board.dialog)[-1] == ("me", "Yes, please.")


def test_replies_wait_until_the_wearer_is_back_home():
    board, _ = with_replies()
    board.handle("clench")  # into I need
    board.heard("Are you comfortable?")
    assert board.state()["screen"] == "menu" and board.state()["path"] == ["I need"]  # not interrupted
    board.handle("clench")  # Water
    board.handle("clench")  # say it
    s = board.state()
    assert s["screen"] == "replies" and s["heard"] == "Are you comfortable?"


def test_the_board_ignores_its_own_voice_and_late_answers():
    board, asked = with_replies()
    for _ in range(3):  # I need > Water > say it
        board.handle("clench")
    board.heard("water please")  # the mic picked up the board saying "Water, please."
    assert board.state()["screen"] == "menu" and asked == []
    board.heard("First question?")
    board.heard("Second question?")
    board.replies_ready(asked[0][2], ["Answer to the first."])  # stale
    assert "Answer to the first." not in [t["label"] for t in board.state()["tiles"]]


def test_go_back_from_replies_to_home():
    board, _ = with_replies()
    board.heard("Hello!")
    board.handle("double_blink")
    board.handle("clench")
    s = board.state()
    assert s["screen"] == "menu" and s["heard"] is None


def test_replies_arriving_keep_the_card_the_wearer_moved_to():
    board, asked = with_replies()
    board.heard("Are you hungry?")
    board.handle("glance_right")  # "No." while the AI is still thinking
    board.replies_ready(asked[0][2], ["Yes, please."])
    s = board.state()
    assert s["tiles"][s["lit"]]["label"] == "No."


def test_an_agent_question_waits_for_home_and_one_bite_answers_it(b):
    b.handle("clench")  # into I need: busy
    b.ask(1, "permission", "Claude wants to run", "npm test", ["Allow", "Deny"])
    assert b.state()["screen"] == "menu" and b.answer_of(1) == (False, None)
    b.handle("double_blink")
    b.handle("clench")  # back home: now it shows
    s = b.state()
    assert s["screen"] == "agent" and s["agent"]["detail"] == "npm test"
    assert [t["label"] for t in s["tiles"]] == ["Allow", "Deny"] and s["tiles"][0]["guess"] and s["lit"] == 0
    b.handle("glance_right")
    b.clock_.t += 2  # the highlight rests on Deny before the jaw closes
    b.handle("clench", ago=GATE_BITE_S)
    assert b.answer_of(1) == (True, "Deny") and b.state()["screen"] == "menu"
    assert b.state()["notice"]["text"] == "Deny: npm test"


def test_going_back_from_an_agent_question_answers_nothing_and_the_next_one_shows(b):
    b.ask(1, "next", "Claude finished", "Fixed the pager.", ["Run the tests", "I'm done"])
    b.ask(2, "permission", "Claude wants to edit", "pager.py", ["Allow", "Deny"])
    assert b.state()["agent"]["kind"] == "next"
    b.handle("double_blink")
    b.handle("clench")
    assert b.answer_of(1) == (True, None) and b.state()["agent"]["detail"] == "pager.py"


def test_help_over_an_agent_question_keeps_it_and_stale_ones_drop(b):
    b.ask(1, "permission", "Claude wants to run", "ls", ["Allow", "Deny"])
    b.handle("long_clench")
    b.clock_.t += HELP_S
    s = b.state()
    assert s["alert"]["text"] == HELP_TEXT and s["screen"] == "agent" and s["agent"]["detail"] == "ls"
    b.clock_.t += 601
    assert b.answer_of(1) == (True, None) and b.state()["screen"] == "menu"


def test_closing_the_eyes_brakes_the_agent_until_the_wearer_says_whats_next(b):
    assert not b.braked()  # Claude checks the brake before each step: it's working
    b.handle("eyes_closed")
    assert b.braked() and b.state()["brake"] and b.state()["notice"]["text"].startswith("Brake on")
    assert b.state()["screen"] == "menu"  # the board itself carries on
    b.ask(1, "next", "Claude finished", "Stopped before editing.", ["Keep going", "I'm done"])
    assert b.state()["agent"]["title"] == "You stopped Claude"
    b.handle("clench")  # Keep going
    assert not b.braked() and b.answer_of(1) == (True, "Keep going")


def test_the_brake_wears_off(b):
    b.braked()
    b.handle("eyes_closed")
    b.clock_.t += 121
    assert not b.braked()


def test_autopilot_runs_alphas_guess_unless_the_wearer_steps_in(b):
    b.ask(1, "permission", "Claude wants to run", "pytest", ["Allow", "Deny"], auto=True)
    assert b.state()["auto_s"] == AUTO_S["permission"] and b.state()["auto_total"] == AUTO_S["permission"]
    b.clock_.t += AUTO_S["permission"]
    assert b.answer_of(1) == (True, "Allow") and b.state()["notice"]["text"] == "Autopilot: Allow · pytest"
    b.ask(2, "permission", "Claude wants to run", "pytest", ["Allow", "Deny"], auto=True)
    b.handle("glance_right")  # choosing by hand: no countdown
    b.clock_.t += 10
    assert b.answer_of(2) == (False, None) and b.state()["auto_s"] is None
    b.handle("clench")  # Deny, picked by hand
    b.ask(3, "permission", "Claude wants to run", "rm -rf build", ["Allow", "Deny"], auto=False)  # risky: waits
    b.clock_.t += 10
    assert b.answer_of(3) == (False, None)


def test_closing_the_eyes_vetoes_the_autopilot(b):
    b.ask(1, "permission", "Claude wants to edit", "pager.py (+1 −1)", ["Allow", "Deny"], auto=True)
    b.handle("eyes_closed")
    assert b.answer_of(1) == (True, "Deny") and b.braked()
    assert b.state()["notice"]["text"] == "Eyes closed: stopped pager.py (+1 −1)"
    b.ask(2, "next", "Claude finished", "Stopped.", ["Run the tests", "I'm done"], auto=True)
    assert b.state()["auto_s"] is None and b.state()["agent"]["title"] == "You stopped Claude"  # braked: no autopilot


def test_autopilot_takes_at_most_three_next_steps_in_a_row(b):
    for qid in range(1, 5):
        b.ask(qid, "next", "Claude finished", "Did it.", ["Commit this", "I'm done"], auto=True)
        b.clock_.t += AUTO_S["next"]
        b.state()  # the hook polls the board meanwhile
    assert [b.answer_of(q) for q in (1, 2, 3)] == [(True, "Commit this")] * 3
    assert b.answer_of(4) == (False, None) and b.state()["auto_s"] is None  # waits for a bite now
    b.handle("clench")
    b.ask(5, "next", "Claude finished", "Did it.", ["Commit this", "I'm done"], auto=True)
    assert b.state()["auto_s"] == AUTO_S["next"]  # a bite resets the count


def test_after_a_no_the_autopilot_waits_for_the_wearer(b):
    b.ask(1, "permission", "Claude wants to run", "git commit -m fix", ["Allow", "Deny"])
    b.handle("glance_right", by="keys")
    b.clock_.t += 2
    b.handle("clench", ago=GATE_BITE_S)  # Deny
    b.ask(2, "next", "Claude finished", "Declined.", ["Retry commit", "Keep going", "I'm done"], auto=True)
    s = b.state()
    assert s["auto_s"] is None and s["agent"]["title"] == "You said no"  # no carrying on with its workaround
    b.handle("glance_right")
    b.handle("clench")  # the wearer's own pick: "Keep going"
    b.ask(3, "next", "Claude finished", "Kept going.", ["Run the tests", "I'm done"], auto=True)
    assert b.state()["auto_s"] == AUTO_S["next"]  # the autopilot is back


def test_eyes_closed_on_whats_next_lights_the_next_guess_and_restarts_the_countdown(b):
    b.ask(1, "next", "Claude finished", "Fixed it.", ["Run the tests", "Commit this", "I'm done"], auto=True)
    b.clock_.t += 4
    b.handle("eyes_closed")  # not that one
    s = b.state()
    assert s["lit"] == 1 and s["auto_s"] == AUTO_S["next"] and not s["brake"]
    assert s["ledger"][-1] == {"what": "Run the tests", "verdict": "no", "by": "brain"}
    b.clock_.t += AUTO_S["next"]
    assert b.answer_of(1) == (True, "Commit this")  # silence: the guess left standing goes
    assert b.state()["ledger"][-1] == {"what": "Commit this", "verdict": "yes", "by": "silence"}


def test_the_ledger_counts_who_decided(b):
    b.ask(1, "permission", "Claude wants to run", "pytest", ["Allow", "Deny"], auto=True)
    b.handle("clench", by="keys")
    b.ask(2, "permission", "Claude wants to run", "git push", ["Allow", "Deny"])
    b.handle("glance_right", by="keys")
    b.clock_.t += 2
    b.handle("clench", ago=GATE_BITE_S)
    s = b.state()
    assert [e["by"] for e in s["ledger"]] == ["keys", "muscle"]
    assert s["counts"] == {"decisions": 2, "wearer": 1, "keys": 2}
    b.braked()  # Claude is working
    b.handle("eyes_closed")
    assert b.state()["ledger"][-1] == {"what": "Stop Claude", "verdict": "stop", "by": "brain"}



def guesses_board():
    guess = lambda label: {"label": label, "phrase": label, "exact": True}  # noqa: E731
    return board_at(Clock(), recall=lambda: [guess("Water, please."), guess("Open the window.")])


def test_mind_reader_answers_unless_the_wearer_closes_their_eyes():
    board, asked = with_replies()
    board.heard("Are you hungry?")
    board.replies_ready(asked[0][2], ["Yes, starving.", "Not right now."])
    assert board.state()["talk_s"] == TALK_S  # rein's best reply, on its ring
    board.handle("eyes_closed")  # no: guess again
    s = board.state()
    assert s["tiles"][s["lit"]]["label"] == "Not right now." and s["talk_s"] == TALK_S and s["said"] is None
    board.clock_.t += TALK_S
    s = board.state()
    assert s["said"]["text"] == "Not right now." and s["screen"] == "menu" and s["talk_s"] is None  # Home stays quiet


def test_eyes_closed_walks_the_guesses_and_backs_out():
    b = guesses_board()
    b.handle("eyes_closed")
    b.handle("eyes_closed")  # past both guesses: "I need" (a folder: no ring)
    assert b.state()["tiles"][b.state()["lit"]]["label"] == "I need" and b.state()["talk_s"] is None
    b.handle("clench")  # yes: in
    assert b.state()["path"] == ["I need"]
    b.handle("eyes_closed")
    b.handle("eyes_closed")  # no to Water, no to Pain: back up
    assert b.state()["path"] == []
    b.handle("glance_right")
    b.handle("glance_right")
    b.handle("clench")
    b.handle("clench")  # Water: the sentence
    assert b.state()["screen"] == "confirm"
    b.handle("eyes_closed")  # don't say it
    assert b.state()["screen"] == "menu" and b.state()["said"] is None


def test_taking_the_headband_off_brakes_a_working_agent_and_denies_what_waits(b):
    b.presence_lost("Headband taken off")
    assert not b.braked()  # no agent was working: nothing to hold back, so the next session isn't blocked
    assert not b.braked()
    b.presence_lost("Headband taken off")
    assert b.braked() and b.state()["notice"]["text"].startswith("Headband taken off")  # Claude had just checked the brake
    assert b.state()["ledger"][-1]["by"] == "presence"


def test_a_nod_says_yes_and_a_shake_says_no_but_a_nod_never_approves_risk(b):
    b.ask(1, "permission", "Claude wants to run", "pytest", ["Allow", "Deny"], True)
    b.handle("nod")
    assert b.answer_of(1) == (True, "Allow") and b.state()["ledger"][-1]["by"] == "head"
    b.ask(2, "permission", "Claude wants to run", "rm -rf build", ["Deny", "Allow"], False)
    b.handle("nod")
    assert b.answer_of(2) == (False, None) and b.state()["notice"]["text"].startswith("A nod can't approve")
    b.handle("shake")
    assert b.answer_of(2) == (True, "Deny") and not b.braked()  # a shake is a no, not a stop
    b.ask(3, "next", "Claude finished", "Done.", ["Run the tests", "Commit this", "I'm done"], True)
    b.handle("shake")
    assert b.answer_of(3) == (False, None)  # not that one: the next guess lights, the question stays


def test_the_board_says_aloud_what_claude_wants_and_when_it_is_stopped(b):
    from src.backend.board import spoken

    q = {"kind": "permission", "title": "Claude wants to edit", "detail": "pager.py (+1 −1)", "options": ["Allow", "Deny"], "auto": True}
    assert spoken(q, True, 6) == "Claude wants to edit pager.py. Going ahead in six seconds."
    assert spoken({**q, "auto": False, "detail": "git commit -m fix"}, False, 6).endswith("This one needs a bite.")
    assert spoken(q, False, 6).endswith("Waiting for you.")  # braked: no countdown to promise
    nxt = {"kind": "next", "title": "Claude finished", "detail": "Done.", "options": ["Run the tests.", "I'm done"], "auto": True}
    assert spoken(nxt, True, 6) == "Claude finished. Next up: run the tests. Going ahead in six seconds."
    assert spoken({**q, "detail": "x " * 80}, True, 6).count("x") <= 36  # a long command isn't read in full
    b.ask(1, "permission", "Claude wants to run", "pytest", ["Allow", "Deny"], True)
    assert b.state()["narrate"]["text"] == "Claude wants to run pytest. Going ahead in six seconds."
    b.braked()
    b.handle("eyes_closed")
    assert b.state()["narrate"]["text"] == "Stopped."


def test_a_risky_step_needs_a_held_bite_to_approve(b):
    b.ask(1, "permission", "Claude wants to run", "git push", ["Allow", "Deny"], auto=False)
    st = b.state()
    assert st["agent"]["gate"] and st["lit"] == 0 and st["auto_s"] is None  # full-screen gate: Allow waits for the bite, nothing counts down
    b.handle("clench", ago=0.6)  # a short bite: a chew, a yawn
    assert b.answer_of(1) == (False, None) and b.state()["notice"]["text"] == "Hold the bite for a full second to approve this."
    b.clock_.t += 60
    assert b.answer_of(1) == (False, None)  # silence never approves
    b.handle("clench", ago=GATE_BITE_S)
    assert b.answer_of(1) == (True, "Allow")
    b.ask(2, "permission", "Claude wants to run", "git push", ["Allow", "Deny"], auto=False)
    b.handle("clench", by="keys")  # the keyboard stand-in has no duration
    assert b.answer_of(2) == (True, "Allow")
    b.ask(3, "permission", "Claude wants to run", "pytest", ["Allow", "Deny"], auto=True)
    assert not b.state()["agent"]["gate"]
    b.handle("clench", by="keys")
    b.ask(4, "permission", "Claude wants to run", "git push", ["Allow", "Deny"], auto=False)
    b.handle("eyes_closed")
    assert b.answer_of(4) == (True, "Deny") and b.braked()  # closing the eyes vetoes it


def test_the_brake_can_be_switched_off_for_hacking(b):
    b.brake_enabled = False
    b.ask(1, "permission", "Claude wants to run", "git push", ["Allow", "Deny"], auto=False)
    b.handle("eyes_closed")
    assert not b.braked() and b.answer_of(1) == (False, None)


def test_camera_only_brake_ignores_the_headband_but_not_the_webcam(b):
    b.brake_enabled, b.camera_only = True, True
    b.ask(1, "permission", "Claude wants to run", "git push", ["Allow", "Deny"], auto=False)
    b.handle("eyes_closed")  # the headband's alpha: ignored in this mode
    assert not b.braked() and b.answer_of(1) == (False, None)
    b.handle("eyes_closed", by="camera")
    assert b.braked() and b.answer_of(1) == (True, "Deny")
