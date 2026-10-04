import json
import sqlite3

import pytest

from src.backend import routines
from src.backend.board import Board, load_menu
from src.backend.history import open_history, record, suggestions


def test_defaults_plus_the_users_file_and_webhooks_only_when_set_up(tmp_path):
    names = [r["name"] for r in routines.load_routines(tmp_path / "none.json", env={})]
    assert "Run the tests" in names and "Run my n8n workflow" not in names  # no webhook URL: no tile that can't work
    assert "Run my n8n workflow" in [r["name"] for r in routines.load_routines(tmp_path / "none.json", env={"N8N_WEBHOOK_URL": "http://x"})]
    mine = tmp_path / "mine.json"
    mine.write_text(json.dumps([{"name": "Run the tests", "kind": "claude", "dir": "demo/web", "mission": "Do it differently."}]))
    assert next(r for r in routines.load_routines(mine, env={}) if r["name"] == "Run the tests")["mission"] == "Do it differently."
    mine.write_text(json.dumps([{"name": "Broken", "kind": "claude"}]))
    with pytest.raises(ValueError):
        routines.load_routines(mine, env={})  # a bad file fails at startup, not mid-demo


def test_the_most_used_routine_comes_first_and_leads_home(tmp_path):
    db = open_history(tmp_path / "h.db")
    rs = routines.load_routines(tmp_path / "none.json", env={})
    for _ in range(3):
        record(db, "Start: Research alpha waves.", "routine", "Research alpha waves")
    record(db, "Start: Run the tests.", "routine", "Run the tests")
    assert routines.ranked(rs, db)[0]["name"] == "Research alpha waves"
    top = suggestions(db)[0]
    assert top["label"] == "Research alpha waves" and top["action"] == "routine" and top["exact"]  # Home offers what you use most


def test_a_routine_tile_confirms_then_runs_and_is_remembered():
    ran, said = [], []
    rs = [{"name": "Run the tests", "kind": "claude", "dir": "demo/pager", "mission": "Run them."}]
    clock = lambda: 100.0  # noqa: E731
    b = Board(load_menu(contacts=[{"name": "Mom"}], routines=rs), clock=clock, act=lambda *a: ran.append(a), remember=lambda *a: said.append(a))
    home = b._tiles()
    assert home[-1]["label"] == "Routines"
    leaf = home[-1]["children"][0]
    assert leaf["action"] == "routine" and leaf["phrase"] == "Start: Run the tests."
    b.stack.append(home[-1])  # open the Routines screen
    b._fresh()
    b.handle("clench")  # a bite takes the lit routine: the confirm screen
    assert b.screen == "confirm"
    b.handle("clench")  # and a second bite confirms it
    assert ran == [("routine", "Start: Run the tests.", "Run the tests")]
    assert said == [("Start: Run the tests.", "routine", "Run the tests")]


def test_start_opens_terminal_on_a_mac_and_just_says_the_command_elsewhere(tmp_path):
    r = {"name": "Run the tests", "kind": "claude", "dir": "demo/pager", "mission": 'Say "hi" and run them.'}
    calls = []
    out = routines.start(r, run=lambda cmd, **kw: calls.append(cmd), platform="darwin")
    assert out.startswith("Started Run the tests") and calls[0][0] == "osascript"
    script = calls[0][2]
    assert "demo/pager" in script and "claude" in script and '\\"hi\\"' in script  # quotes survive AppleScript and the shell
    assert routines.start(r, platform="linux").startswith("Run this to start Run the tests: cd ")
    hook = {"name": "n8n", "kind": "webhook", "url": "http://x"}
    assert routines.start(hook).startswith("Would start n8n")  # demo mode: nothing is sent


def test_the_three_pillars_ship_as_default_routines(tmp_path):
    rs = routines.load_routines(tmp_path / "none.json", env={})
    names = [r["name"] for r in rs]
    for name in ("Find lunch", "Morning briefing", "Room remote"):
        assert name in names
        r = next(x for x in rs if x["name"] == name)
        assert r["kind"] == "claude" and r["mission"] and r["dir"]  # schema: load would have raised
    assert len(names) <= routines.MAX
