import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.backend import server
from src.backend.coach import SAMPLE_EVERY_S, open_db


@pytest.fixture
def api(tmp_path, monkeypatch):
    db = tmp_path / "c.db"
    open_db(db).close()
    s = server.Session()
    s.db_path, s.phase = db, "connected"
    s.coach = SimpleNamespace(state={"live": True, "error": None}, want_calibration=False)
    monkeypatch.setattr(server, "session", s)
    return TestClient(server.app, base_url="http://127.0.0.1:8000"), db


def test_app_summary_rates(api):
    _, db_path = api
    now = time.time()
    with sqlite3.connect(db_path) as db:
        db.executemany("INSERT INTO samples (ts, app, tilt, hr) VALUES (?,?,?,?)",
                       [(now - SAMPLE_EVERY_S * i, "Zoom", 20.0, 70.0) for i in range(60 // SAMPLE_EVERY_S)])
        db.executemany("INSERT INTO events VALUES (?,?,?,?)",
                       [(now - i, "blink", 1, "Zoom") for i in range(6)]
                       + [(now - 30, "clench", 2.0, "Zoom"), (now - 20, "nudge_clench", 0, "Zoom"), (now - 10, "nudge_blink", 0, "Zoom")])
    assert server.app_summary() == [{"app": "Zoom", "minutes": 1.0, "blinks_per_min": 6.0, "clenches_per_hour": 60.0,
                                     "clench_seconds": 2.0, "avg_tilt": 20.0, "avg_hr": 70.0, "nudges": 2}]


def test_nerd_stats_without_a_live_headband(api):
    client, _ = api
    assert client.get("/api/nerd").json() == {"live": False, "phase": "connected"}


def test_rejects_foreign_host_and_cross_site_writes(api):
    client, _ = api
    assert client.get("/api/state", headers={"host": "rebind.evil.example:8000"}).status_code == 400
    assert client.post("/api/calibrate", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/calibrate", headers={"origin": "http://127.0.0.1:8000"}).status_code == 200
    assert server.session.coach.want_calibration


def test_lock_screen_scan_connect_disconnect(tmp_path, monkeypatch):
    s = server.Session(simulated=True)
    s.db_path = tmp_path / "sim.db"
    monkeypatch.setattr(server, "session", s)
    client = TestClient(server.app, base_url="http://127.0.0.1:8000")
    assert client.get("/api/state").json()["phase"] == "locked"
    assert client.post("/api/calibrate").status_code == 409  # nothing connected yet
    devices = client.post("/api/scan").json()["devices"]
    assert [d["name"] for d in devices] == ["Muse-SIM"] and devices[0]["simulated"]
    assert client.post("/api/connect", json={"name": "Ganglion-1"}).status_code == 400
    assert client.post("/api/connect", json={"name": "Muse-SIM"}).status_code == 200
    for _ in range(50):
        if s.phase == "connected":
            break
        time.sleep(0.05)
    state = client.get("/api/state").json()
    assert state["phase"] == "connected" and state["device"]["name"] == "Muse-SIM"
    assert client.post("/api/disconnect").status_code == 200
    assert client.get("/api/state").json()["phase"] == "locked"


def board_with_demo_contacts():
    return server.Board(server.load_menu(contacts=server.actions.DEMO_CONTACTS))


@pytest.fixture
def connected(monkeypatch):
    """A headband is connected, so the board takes input."""
    s = server.Session(simulated=True)
    s.phase = "connected"
    monkeypatch.setattr(server, "session", s)
    monkeypatch.setattr(server, "board", board_with_demo_contacts())
    return TestClient(server.app, base_url="http://127.0.0.1:8000")


def test_board_app_is_served_once_built(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "UI", tmp_path)
    client = TestClient(server.app, base_url="http://127.0.0.1:8000")
    assert client.get("/").status_code == 503 and "npm run build" in client.get("/").text
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    assert client.get("/").text == '<div id="root"></div>' and client.get("/board").status_code == 200


def test_board_is_gated_on_a_connected_headband(monkeypatch):
    monkeypatch.setattr(server, "session", server.Session(simulated=True))
    monkeypatch.setattr(server, "board", board_with_demo_contacts())
    client = TestClient(server.app, base_url="http://127.0.0.1:8000")
    assert client.get("/api/board").json()["headband"]["phase"] == "locked"
    assert client.post("/api/input", json={"kind": "clench"}).status_code == 409
    assert client.get("/api/board").json()["path"] == []  # nothing got through
    assert "Screen Body Coach" in client.get("/coach").text


def test_board_keyboard_input(connected):
    client = connected
    assert client.get("/board").status_code == 200
    assert client.post("/api/input", json={"kind": "glance_right"}).json()["lit"] == 1
    assert client.post("/api/input", json={"kind": "glance_left"}).json()["lit"] == 0
    assert client.post("/api/input", json={"kind": "clench"}).json()["path"] == ["I need"]
    assert client.get("/api/board").json()["path"] == ["I need"]
    assert client.post("/api/input", json={"kind": "wink"}).status_code == 422
    assert client.post("/api/input", json={"kind": "clench", "ago": 99}).status_code == 422
    assert client.post("/api/input", json={"kind": "clench"}, headers={"origin": "https://evil.example"}).status_code == 403


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")  # the crash is the point
def test_an_ai_crash_still_answers_the_board(monkeypatch):
    b = server.Board(server.load_menu(contacts=server.actions.DEMO_CONTACTS), suggest=server.suggest)
    monkeypatch.setattr(server, "board", b)

    def crash(*a):
        raise RuntimeError("bug")

    monkeypatch.setattr(server, "ai_options", crash)
    b.handle("clench")
    b.handle("clench")  # I need > Water
    for _ in range(200):
        if b.state()["screen"] == "confirm":
            break
        time.sleep(0.01)
    assert b.state()["sentence"] == "Could I have some water, please?"


def test_speech_only_voices_what_the_board_said(connected, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    client = connected
    assert client.get("/api/speech/999").status_code == 404
    for _ in range(2):  # I need > Water
        client.post("/api/input", json={"kind": "clench"})
    said = client.post("/api/input", json={"kind": "clench"}).json()["said"]
    assert client.get(f"/api/speech/{said['id']}").status_code == 204  # no key: the page uses the browser voice


def test_heard_is_gated_and_opens_replies(connected, monkeypatch):
    client = connected
    monkeypatch.setattr(server, "session", server.Session(simulated=True))  # nothing connected
    assert client.post("/api/heard", json={"text": "Hi there"}).status_code == 409
    s = server.Session(simulated=True)
    s.phase = "connected"
    monkeypatch.setattr(server, "session", s)
    body = client.post("/api/heard", json={"text": "Hi there"}).json()
    assert body["screen"] == "replies" and body["heard"] == "Hi there"
    assert client.post("/api/heard", json={"text": ""}).status_code == 422


def test_logo_files_are_served():
    client = TestClient(server.app, base_url="http://127.0.0.1:8000")
    for path in ("/alpha-logo.svg", "/alpha-mark.svg"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and "<svg" in r.text


def test_agent_questions_go_through_the_board(connected, monkeypatch):
    client = connected
    ask = {"kind": "permission", "title": "Claude wants to run", "detail": "npm test", "options": ["Allow", "Deny"]}
    qid = client.post("/api/agent/ask", json=ask).json()["id"]
    assert client.get(f"/api/agent/answer/{qid}").json() == {"done": False, "answer": None}
    assert client.get("/api/board").json()["agent"]["detail"] == "npm test"
    client.post("/api/input", json={"kind": "clench"})
    assert client.get(f"/api/agent/answer/{qid}").json() == {"done": True, "answer": "Allow"}
    assert client.post("/api/agent/ask", json={**ask, "options": []}).status_code == 422
    monkeypatch.setattr(server, "session", server.Session(simulated=True))  # no headband
    assert client.post("/api/agent/ask", json=ask).status_code == 409  # the hook steps aside


def test_eyes_closed_from_the_keyboard_turns_the_brake_on(connected):
    client = connected
    assert client.get("/api/agent/brake").json() == {"on": False}
    assert client.post("/api/input", json={"kind": "eyes_closed"}).json()["brake"]
    assert client.get("/api/agent/brake").json() == {"on": True}


def test_only_the_simulator_closes_its_eyes_on_command(monkeypatch):
    s = server.Session(simulated=True)
    monkeypatch.setattr(server, "session", s)
    client = TestClient(server.app, base_url="http://127.0.0.1:8000")
    assert client.post("/api/sim/eyes", json={"closed": True}).status_code == 409  # nothing connected
    s.source = server.SimSource(seed=0)
    assert client.post("/api/sim/eyes", json={"closed": True}).json() == {"closed": True} and s.source.eyes_closed


def test_claude_code_hooks_only_act_while_the_floating_window_arms_alpha(connected, monkeypatch):
    import threading

    client = connected
    hook = lambda event: client.post("/api/hooks", json={"hook_event_name": event, "tool_name": "Bash",  # noqa: E731
                                                         "tool_input": {"command": "pytest"}, "last_assistant_message": "Done."})
    monkeypatch.setattr(server, "armed_until", 0.0)
    r = hook("SessionStart")
    assert r.status_code == 200 and r.content == b""  # not armed: Claude Code carries on as usual
    assert client.post("/api/agent/arm").json() == {"armed": True}
    assert "Next:" in hook("SessionStart").json()["hookSpecificOutput"]["additionalContext"]
    assert hook("PreToolUse").content == b""  # no brake
    client.post("/api/input", json={"kind": "eyes_closed"})
    assert hook("PreToolUse").json()["hookSpecificOutput"]["permissionDecision"] == "deny"
    server.board.brake_until = 0.0
    threading.Timer(0.5, lambda: server.board.handle("clench")).start()  # the wearer bites Allow
    assert hook("PermissionRequest").json()["hookSpecificOutput"]["decision"] == {"behavior": "allow"}


def test_a_brake_in_force_survives_the_floating_window_closing(connected, monkeypatch):
    client = connected
    hook = lambda event: client.post("/api/hooks", json={"hook_event_name": event, "tool_name": "Bash",  # noqa: E731
                                                         "tool_input": {"command": "pytest"}})
    client.post("/api/agent/arm")
    assert hook("PreToolUse").content == b""  # Claude is working: eyes closed now brakes it
    client.post("/api/input", json={"kind": "eyes_closed"})
    monkeypatch.setattr(server, "armed_until", 0.0)  # the window closes with the wearer's eyes shut
    assert hook("PreToolUse").json()["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hook("PermissionRequest").content == b""  # everything else steps aside, as before
    server.board.brake_until = 0.0
    assert hook("PreToolUse").content == b""  # no brake, no window: Claude Code carries on


def test_gaze_config_and_cross_origin_isolation(connected, monkeypatch):
    client = connected
    monkeypatch.delenv("EYEDID_LICENSE_KEY", raising=False)
    assert client.get("/api/gaze/config").json() == {"key": None}  # no key: the page falls back to the mouse
    monkeypatch.setenv("EYEDID_LICENSE_KEY", "dev_test")
    r = client.get("/api/gaze/config")
    assert r.json() == {"key": "dev_test"}
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin"  # SharedArrayBuffer needs both headers
    assert r.headers["Cross-Origin-Embedder-Policy"] == "credentialless"


def test_the_camera_can_brake_but_only_by_seeing_eyes_close(connected):
    client = connected
    assert client.post("/api/input", json={"kind": "clench", "by": "camera"}).status_code == 422
    client.post("/api/agent/arm")
    client.post("/api/hooks", json={"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "pytest"}})
    assert client.post("/api/input", json={"kind": "eyes_closed", "by": "camera"}).status_code == 200
    assert server.board.state()["ledger"][-1]["by"] == "camera"  # labeled as the camera, never as BRAIN
