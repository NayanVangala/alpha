"""The patient board: big cards, moved with the eyes and picked with a jaw clench.

- Every screen opens on its best guess: what the wearer usually says around
  this time of day, the AI's fullest sentence, or its likeliest reply. A glance
  left or right moves to the next card; nothing moves on a timer. A clench
  picks the card that was lit when the clench began, so a glance that slipped
  in mid-clench can't steal the pick. (`scan_s` brings back the old
  highlight-steps-on-its-own scan, for anyone whose glances don't read.)
- Picking a tile with no children shows its sentence and what will happen
  (say it, text someone, call someone). One more clench does it; nothing is
  said or sent without that confirm. Before a spoken sentence, the AI may
  offer up to three fuller ways to say it next to the plain one; a clench
  while it's still thinking takes the plain one.
- A double blink opens "Go back?". A clench within BACK_S goes back; doing
  nothing stays.
- A long clench starts a HELP_S countdown from any screen, a double blink
  cancels it, and at zero it raises the help alert and texts and calls the
  help contact. No AI on this path.
- Conversation mode: when someone in the room says something, the board
  shows a Reply screen with the AI's suggested answers and a few fixed ones.
  It waits until the wearer is back at Home rather than interrupting a pick,
  and ignores anything that matches what the board itself just said.
- A coding agent (Claude Code, through its hooks) can ask a question: allow
  this command or edit, or what to do next. It waits for Home like a reply
  does, shows its options as cards, and one bite answers it. Going back
  answers nothing, so Claude Code falls back to asking on screen.
- Eyes closed (the alpha rhythm rising, the one brain signal used) means no.
  On the agent's "what next" card it lights the next guess and restarts the
  countdown; while the agent is working it's the brake: the agent stops
  before its next step and asks what's next.
- Every agent decision goes in a short ledger (what, yes / no / stop, and
  whether brain, muscle, silence or the keyboard decided it), with counts.
- Autopilot: an agent question that's safe to guess runs its first card,
  Alpha's guess, after a short countdown. The wearer only steps in when it's
  wrong: closing the eyes vetoes it, a glance takes over by hand, a bite does
  it now. Risky commands never run by themselves, and after the wearer says
  no, or after a few automatic "what next" steps in a row, Alpha waits for a
  bite instead of following the agent's next guess.
"""

import json
import math
import re
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path

MENU = Path(__file__).with_name("menu.json")
MAX_TILES = 6
SCAN_S = 1.6  # the scan fallback's dwell. ponytail: one for everyone; make it per-person once real users try it
PICK_PAUSE_S = 0.8  # extra time on the first tile after the screen changes
BACK_S = 3.0
HELP_S = 5.0
MAX_LOOKBACK_S = 3.0
FINDING_S = 5.0  # longest the board waits for AI options before using the plain sentence
HELP_TEXT = "I need help now."
GUESSES = 3  # sentences from history that lead Home
QUICK_REPLIES = ("Yes.", "No.", "Can you say that again?")  # always there, with or without the AI
ASK_S = 600  # an agent question nobody answered is dropped after this (Claude Code's hook gives up then too)
BRAKE_S = 120  # eyes closed holds the agent this long, or until the wearer says what's next
# autopilot: Alpha does its guess after this unless the wearer steps in. Long enough for a real brain to veto:
# on 109 people's EEG the eyes-closed brake typically fired about 5 s after the eyes shut.
AUTO_S = {"permission": 6.0, "next": 6.0}
AUTO_NEXT_MAX = 3  # automatic "what next" steps in a row before Alpha waits for a bite
TALK_S = 6.0  # mind reader: a guessed sentence is said after this unless the wearer closes their eyes
AGENT_BUSY_S = 10.0  # Claude checked the brake this recently: it's working, so eyes closed brakes it


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def contact_tiles(name):
    return [
        {"label": "Come here", "phrase": "Please come here.", "action": "text", "to": name},
        {"label": "I'm okay", "phrase": "I'm okay, don't worry.", "action": "text", "to": name},
        {"label": "Call me", "phrase": "Please call me when you can.", "action": "text", "to": name},
        {"label": "Call now", "phrase": "Please come, I need you.", "action": "call", "to": name},
    ]


def load_menu(path=MENU, contacts=()):
    """Menu tree from JSON, with People filled from contacts. A bad file fails at startup, not mid-demo."""
    menu = json.loads(Path(path).read_text())

    def check(node, where):
        if node.pop("from_contacts", False):
            node["children"] = [{"label": c["name"], "children": contact_tiles(c["name"])} for c in contacts]
        kids = node.get("children")
        if kids is None:
            if not node.get("phrase"):
                raise ValueError(f"{where}: a tile with no children needs a phrase")
            return
        if not 1 <= len(kids) <= MAX_TILES:
            raise ValueError(f"{where}: needs 1 to {MAX_TILES} tiles, has {len(kids)}")
        for k in kids:
            check(k, f"{where} > {k['label']}")

    check(menu, menu.get("label", "Home"))
    return menu


class Board:
    def __init__(self, menu, clock=time.monotonic, scan_s=None, act=None, suggest=None, remember=None, recall=None,
                 reply=None):
        self.menu, self.clock = menu, clock
        self.scan_s = scan_s  # None: glances move the highlight. Seconds: it steps on its own (the fallback)
        self.act = act or (lambda kind, text, to: None)  # ("text" | "call" | "help", text, contact); must not block
        # (path, phrase, token, recent) -> None; must not block, and must answer via options_ready(token, ...)
        self.suggest = suggest
        self.remember = remember or (lambda sentence, action, to: None)  # every confirmed output
        self.recall = recall or (lambda: [])  # finished-sentence tiles to lead Home with, most likely first
        self.took = None  # {"id": output id, "n": clenches, "glances": glances, from Home to confirm}
        # (heard, dialog, token) -> None; must not block, and must answer via replies_ready(token, ...)
        self.reply = reply
        self.dialog = deque(maxlen=12)  # ("them" | "me", text), oldest first: context for the replies
        self.heard_text = self.pending_heard = self.replies = None
        self.reply_token = 0
        self.lock = threading.RLock()
        self.n_out = self.token = 0
        self.said = self.alert = self.notice = None  # latest {"id", "text"}; the page shows or voices each id once
        self.recent = OrderedDict()  # id -> text of recent outputs, so /api/speech only voices what the board said
        self.said_log = deque(maxlen=20)  # context for the AI's options
        self.asks = deque()  # agent questions waiting for the wearer to be free
        self.question = None  # the agent question on screen
        self.answers = OrderedDict()  # question id -> the picked option, or None when the wearer went back
        self.brake_until = 0.0  # the agent may not take another step before this
        self.auto_at = None  # when the agent question on screen answers itself with Alpha's guess
        self.auto_streak = 0  # automatic "what next" answers since the wearer last picked one
        self.talk_at = None  # when the guessed sentence on screen says itself
        self.moves = [(clock(), 0)]  # (when, card) each time the highlight moved, for the clench lookback
        self.stack, self.screen = [menu], "menu"
        self.agent_seen = -1e9  # last time the coding agent checked the brake (it does before every step)
        self.declined = False  # the wearer just said no: the autopilot doesn't carry on with the agent's guess
        self.auto_card = 0  # the card the autopilot will do
        self.ledger = deque(maxlen=8)  # latest agent decisions, for the page
        self.counts = {"decisions": 0, "wearer": 0, "keys": 0}  # wearer: headband inputs; keys: keyboard ones
        self._home()

    # -- internals, called with the lock held --

    def _home(self):
        if self.question:  # left unanswered (help went off over it): it waits its turn again
            self.asks.appendleft(self.question)
            self.question = None
        home = {"label": self.menu["label"], "children": self.recall()[:GUESSES] + self.menu["children"]}
        self.stack, self.screen = [home], "menu"
        self.leaf = self.sentence = self.options = self.heard_text = None
        self.finding_until, self.clenches, self.glances = 0.0, 0, 0
        self._fresh()
        if self.pending_heard:  # someone spoke while the wearer was busy: answer it now
            self._show_replies()
        elif self.asks:  # the agent asked something meanwhile
            self._show(self.asks.popleft())

    def _show_replies(self):
        self.screen, self.heard_text, self.pending_heard = "replies", self.pending_heard, None
        self._fresh()

    def _confirm(self, sentence):
        self.screen, self.sentence, self.options = "confirm", sentence, None

    def _close(self):
        """Drop any overlay. A glance highlight stays where it was; the scan starts over from the first tile."""
        self.overlay = self.deadline = None
        self.scan_from = self.clock() + PICK_PAUSE_S
        self._arm_talk()

    def _fresh(self):
        """New cards on screen: drop any overlay and light the first one, the best guess."""
        self._close()
        self.moves = [(self.clock(), 0)]  # (when, card) each time the highlight moved, for the clench lookback
        self._arm_talk()

    def _lit_tile(self):
        tiles = self._tiles() if self.screen in ("menu", "options", "replies") else []
        return tiles[self._lit_at(self.clock())] if tiles else None

    def _arm_talk(self):
        """Mind reader: an answer to something (a reply to what was just said, or the AI's sentence for a pick)
        says itself after TALK_S. Home's guesses wait for a bite, or they'd keep talking to an empty room."""
        t = self._lit_tile() if not self.scan_s else None
        self.talk_at = self.clock() + TALK_S if t is not None and self.screen in ("options", "replies") else None

    def _do(self, sentence, leaf):
        """Say it (or text or call), log it, and go Home."""
        action = leaf.get("action", "speak")
        if action == "speak":
            self._out("said", sentence)
            self.said_log.append(sentence)
            self.dialog.append(("me", sentence))
        else:
            self._out("notice", f"{'Texting' if action == 'text' else 'Calling'} {leaf['to']}…")
            self.act(action, sentence, leaf["to"])
        self.took = {"id": self.n_out, "n": self.clenches, "glances": self.glances}
        self.remember(sentence, action, leaf.get("to"))
        self._home()

    def _back(self):
        """Back from a sentence (or the replies) to the tiles that led to it, or up a level."""
        if self.screen != "menu":
            self.screen, self.leaf, self.sentence, self.options = "menu", None, None, None
            self.heard_text = None
        elif len(self.stack) > 1:
            self.stack.pop()
        if self.screen == "menu" and len(self.stack) == 1:
            self._home()  # back at Home: anything that waited for it shows now
        else:
            self._fresh()

    def _open(self, overlay, seconds):
        self.overlay, self.deadline = overlay, self.clock() + seconds

    def _show(self, q):
        """Put an agent question on screen, with the autopilot countdown when its guess is safe to run."""
        self.question, self.screen = q, "agent"
        self._fresh()
        braked = self.clock() < self.brake_until
        # after a no, or a few automatic steps in a row, what happens next is the wearer's call (see _arm_auto)
        if q["kind"] == "next" and self.declined and not braked:
            q["title"] = "You said no"
        self._arm_auto(0)

    def _arm_auto(self, card):
        """Alpha does `card` after the countdown, unless the agent is braked or it's the wearer's call."""
        q = self.question
        braked = self.clock() < self.brake_until
        hold = q["kind"] == "next" and (self.declined or self.auto_streak >= AUTO_NEXT_MAX)
        self.auto_card = card
        self.auto_at = self.clock() + AUTO_S[q["kind"]] if q["auto"] and not braked and not hold else None

    def _note(self, what, verdict, by):
        """One ledger line: what was decided, yes / no / stop, by brain, muscle, silence or keys."""
        self.ledger.append({"what": what[:80], "verdict": verdict, "by": by})
        self.counts["decisions"] += 1

    def _answer(self, answer):
        """Settle the agent question on screen, then carry on with whatever waits."""
        self.auto_at = None
        self.answers[self.question["id"]] = answer
        while len(self.answers) > 50:
            self.answers.popitem(last=False)
        self.question = None
        self._home()

    def _tiles(self):
        if self.screen == "agent":
            return [{"label": o, "guess": i == 0} for i, o in enumerate(self.question["options"])]
        if self.screen == "options":
            return [{"label": o, "guess": o != self.leaf["phrase"]} for o in self.options or []]
        if self.screen == "replies":
            ai = self.replies or []
            return [{"label": r, "guess": r in ai} for r in dict.fromkeys([*ai, *QUICK_REPLIES])][:MAX_TILES]
        return self.stack[-1]["children"]

    def _lit_at(self, t):
        """Card lit at time t: where the glances had put it, or (scan) one step per scan_s after a pause."""
        n = len(self._tiles())
        if not n:
            return None
        if self.scan_s:
            return max(0, math.floor((t - self.scan_from) / self.scan_s)) % n
        return next((i for when, i in reversed(self.moves) if when <= t), self.moves[0][1]) % n

    def _out(self, kind, text):
        self.n_out += 1
        setattr(self, kind, {"id": self.n_out, "text": text})
        self.recent[self.n_out] = text
        while len(self.recent) > 20:
            self.recent.popitem(last=False)

    # -- public --

    def tick(self):
        """Run out the overlay timers. Called before every read and input."""
        with self.lock:
            if self.screen == "options" and self.options is None and self.clock() >= self.finding_until:
                self._confirm(self.leaf["phrase"])  # the AI never answered: don't leave them waiting
            now = self.clock()
            if self.screen == "agent" and self.auto_at is not None and now >= self.auto_at and not self.overlay:
                picked, q = self._tiles()[self.auto_card]["label"], self.question  # the guess left standing
                if q["kind"] == "next":
                    self.auto_streak += 1
                    self.brake_until = 0.0
                    self._note(picked, "yes", "silence")
                else:
                    self.declined = False  # it was allowed
                    self._note(q["detail"], "yes", "silence")
                self._out("notice", f"Autopilot: {picked}" + (f" · {q['detail'][:60]}" if q["kind"] == "permission" else ""))
                self._answer(picked)
            if self.talk_at is not None and now >= self.talk_at and not self.overlay:
                t = self._lit_tile()
                if t is not None:
                    self.talk_at = None
                    leaf = {"label": "Reply", "phrase": t["label"]} if self.screen == "replies" else \
                        t if self.screen == "menu" else self.leaf
                    self._do(t["label"], leaf)
            self.asks = deque(q for q in self.asks if q["until"] > now)
            if self.question and self.question["until"] <= now and not self.overlay:
                self._answer(None)  # the agent stopped waiting long ago
            if self.overlay and self.clock() >= self.deadline:
                if self.overlay == "help":
                    self._out("alert", HELP_TEXT)
                    self.act("help", HELP_TEXT, None)
                    self._home()
                else:
                    self._close()  # no clench on "Go back?" means stay

    def handle(self, kind, ago=0.0, by="headband"):
        """kind: clench | long_clench | double_blink | glance_left | glance_right | eyes_closed.

        ago: seconds since the clench began. by: "headband", or "keys" for the keyboard stand-in.
        """
        with self.lock:
            self.tick()
            self.counts["keys" if by == "keys" else "wearer"] += 1
            who = by if by in ("keys", "camera") else "head" if kind in ("nod", "shake") else "brain" if kind == "eyes_closed" else "muscle"
            if kind in ("nod", "shake"):  # a nod says yes and a shake says no, on Claude's questions only
                if self.screen != "agent" or self.overlay:
                    return
                q = self.question
                if kind == "nod":
                    if q["kind"] == "permission" and not q["auto"]:
                        self._out("notice", "A nod can't approve a risky step: bite down.")
                        return
                    kind = "clench"  # the lit guess, as a bite would take it
                elif q["kind"] == "next":
                    kind = "eyes_closed"  # not that one: the next guess (this path never brakes)
                else:
                    self._note(q["detail"], "no", who)
                    self._out("notice", f"Shook no: {q['detail'][:60]}")
                    self.declined = True
                    self._answer("Deny")
                    return
            if kind != "clench":
                self.auto_at = None  # the wearer is steering this one by hand
            if kind == "long_clench":
                if self.overlay != "help":
                    self._open("help", HELP_S)
            elif kind == "double_blink":
                if self.overlay:
                    self._close()  # cancels help, or answers "stay" to "Go back?"
                elif self.screen != "menu" or len(self.stack) > 1:
                    self._open("back", BACK_S)
            elif kind == "clench":
                if self.overlay == "help":
                    return  # the countdown is the confirm; only a double blink stops it
                ago = min(max(ago, 0.0), MAX_LOOKBACK_S)
                self.clenches += 1
                if self.overlay == "back" and self.screen == "agent":
                    self._answer(None)  # no answer: Claude Code asks on its own screen instead
                elif self.overlay == "back":
                    self._back()
                elif self.screen == "confirm":
                    self._do(self.sentence, self.leaf)
                elif self.screen == "options":
                    tiles = self._tiles()
                    # still finding options: a clench takes the plain sentence right away
                    self._confirm(tiles[self._lit_at(self.clock() - ago)]["label"] if tiles else self.leaf["phrase"])
                elif self.screen == "agent":
                    picked = self._tiles()[self._lit_at(self.clock() - ago)]["label"]
                    kind = self.question["kind"]
                    self._note(picked if kind == "next" else self.question["detail"],
                               "yes" if kind == "next" or picked == "Allow" else "no", who)
                    self._out("notice", f"{picked}: {self.question['detail'][:60]}" if kind == "permission" else f"Told Claude: {picked}")
                    if kind == "next":
                        self.brake_until = 0.0  # they've said what's next: the brake comes off
                        self.declined, self.auto_streak = False, 0  # their own instruction: the autopilot may resume
                    else:
                        self.declined = picked != "Allow"
                    self._answer(picked)
                elif self.screen == "replies":
                    text = self._tiles()[self._lit_at(self.clock() - ago)]["label"]
                    self.leaf = {"label": "Reply", "phrase": text}
                    self._confirm(text)
                else:
                    tile = self._tiles()[self._lit_at(self.clock() - ago)]
                    if "children" in tile:
                        self.stack.append(tile)
                        self._fresh()
                    else:
                        self.leaf = tile
                        if tile.get("action", "speak") == "speak" and self.suggest and not tile.get("exact"):
                            self.token += 1
                            self.screen, self.options = "options", None
                            self.finding_until = self.clock() + FINDING_S
                            self._fresh()
                            path = [n["label"] for n in self.stack[1:]] + [tile["label"]]
                            self.suggest(path, tile["phrase"], self.token, list(self.said_log))
                        else:
                            self._confirm(tile["phrase"])
            elif kind == "eyes_closed":  # "no": cancels help, brakes a working agent, or "not that, guess again"
                if self.overlay == "help":
                    self._close()  # cancelled
                    return
                if self.screen == "agent" and not self.overlay and self.question["kind"] == "next":
                    tiles, lit = self._tiles(), self._lit_at(self.clock())
                    self._note(tiles[lit]["label"], "no", who)  # not that one: Alpha moves to its next guess
                    self.moves.append((self.clock(), (lit + 1) % len(tiles)))
                    del self.moves[:-20]
                    self._arm_auto((lit + 1) % len(tiles))
                    return
                if self.screen != "agent" and self.clock() - self.agent_seen > AGENT_BUSY_S:
                    if self.overlay:
                        return
                    if self.screen == "confirm":
                        self._back()  # don't say it
                        return
                    n = len(self._tiles())
                    lit = self._lit_at(self.clock())
                    if n and lit == n - 1 and (self.screen != "menu" or len(self.stack) > 1):
                        self._back()  # no to every guess here: up a level
                    elif n:
                        self.moves.append((self.clock(), (lit + 1) % n))  # the next guess
                        self._arm_talk()
                    return
                newly = self.clock() >= self.brake_until
                if newly:
                    self._out("notice", "Brake on: Claude stops before its next step.")
                self.brake_until = self.clock() + BRAKE_S
                if self.screen == "agent" and not self.overlay:  # a permission card (a next card returned above)
                    self._out("notice", f"Eyes closed: stopped {self.question['detail'][:60]}")
                    self._note(self.question["detail"], "no", who)
                    self.declined = True
                    self._answer("Deny")  # vetoed: it doesn't happen
                elif newly:
                    self._note("Stop Claude", "stop", who)
            elif kind in ("glance_left", "glance_right"):
                n = len(self._tiles()) if self.screen != "confirm" else 0
                if n and not self.overlay and not self.scan_s:
                    now = self.clock()
                    self.glances += 1
                    self.moves.append((now, (self._lit_at(now) + (1 if kind == "glance_right" else -1)) % n))
                    del self.moves[:-20]  # the lookback only needs the last few seconds
                    self._arm_talk()
            else:
                raise ValueError(f"unknown input {kind!r}")

    def options_ready(self, token, found):
        """The AI's sentences for the pick on the options screen, then the plain one. Late answers are dropped."""
        with self.lock:
            if token != self.token or self.screen != "options" or self.options is not None:
                return
            choices = list(dict.fromkeys([*found, self.leaf["phrase"]]))
            if len(choices) == 1:
                self._confirm(choices[0])  # nothing extra to choose from
            else:
                self.options = choices
                self._fresh()

    def heard(self, text):
        """Someone in the room said `text`. Replies show now if the wearer is at Home, else once they're back."""
        with self.lock:
            if _norm(text) in {_norm(t) for t in self.recent.values()}:
                return  # the board hearing its own voice
            self.dialog.append(("them", text))
            self.pending_heard, self.replies = text, None
            self.reply_token += 1
            if self.reply:
                self.reply(text, list(self.dialog), self.reply_token)
            if self.screen in ("menu", "replies") and len(self.stack) == 1 and not self.overlay and not self.question:
                self._show_replies()

    def replies_ready(self, token, found):
        """The AI's replies to the latest thing heard, shown before the fixed ones. Late answers are dropped."""
        with self.lock:
            if token != self.reply_token:
                return
            lit = self._lit_at(self.clock()) if self.screen == "replies" and not self.scan_s else None
            was = self._tiles()[lit]["label"] if lit else None  # the wearer already glanced off the first card
            self.replies = list(found)
            if self.screen == "replies":
                labels = [t["label"] for t in self._tiles()]
                # stay on the reply they moved to; otherwise lead with the AI's best guess
                self.moves = [(self.clock(), labels.index(was) if was in labels else 0)]
                if not self.overlay:
                    self._close()  # the scan starts over on the new cards

    def ask(self, qid, kind, title, detail, options, auto=False):
        """A question from the coding agent. Shown now if the wearer is at Home, else once they're back.

        kind: "permission" (allow a command or edit) or "next" (what to do next). The first option is
        the board's guess and is lit first. auto: safe for the autopilot to run that guess by itself.
        The answer waits in `answers` until the agent collects it.
        """
        with self.lock:
            self.tick()  # a countdown that ran out goes first
            if kind == "next" and self.clock() < self.brake_until:
                title = "You stopped Claude"
            q = {"id": qid, "kind": kind, "title": title, "detail": detail,
                 "options": list(dict.fromkeys(options))[:MAX_TILES], "until": self.clock() + ASK_S, "auto": auto}
            if self.screen == "menu" and len(self.stack) == 1 and not self.overlay:
                self._show(q)
            else:
                self.asks.append(q)

    def presence_lost(self, reason):
        """The headband came off or went quiet: fail closed. A working agent is held back and a pending permission is
        denied. Nothing happens when no agent is working, so taking the band off at day's end blocks no one."""
        with self.lock:
            self.tick()
            if self.screen != "agent" and self.clock() - self.agent_seen > AGENT_BUSY_S:
                return
            newly = self.clock() >= self.brake_until
            self.brake_until = self.clock() + BRAKE_S
            self._out("notice", f"{reason}: Claude stops before its next step.")
            if self.screen == "agent" and not self.overlay and self.question["kind"] == "permission":
                self._note(self.question["detail"], "no", "presence")
                self.declined = True
                self._answer("Deny")
            elif newly:
                self._note("Stop Claude", "stop", "presence")

    def braked(self):
        """True while the wearer's closed eyes hold the agent back. The agent asks before every step."""
        with self.lock:
            self.agent_seen = self.clock()
            return self.clock() < self.brake_until

    def answer_of(self, qid):
        """(answered, answer). The answer is None when the wearer went back without picking."""
        with self.lock:
            self.tick()
            return (qid in self.answers, self.answers.get(qid))

    def notify(self, text):
        """A result line from a text or call that finished in the background."""
        with self.lock:
            self._out("notice", text)

    def text_of(self, out_id):
        with self.lock:
            return self.recent.get(out_id)

    def state(self):
        with self.lock:
            self.tick()
            now = self.clock()
            tiles = self._tiles() if self.screen != "confirm" else []
            lit = self._lit_at(now) if tiles and not self.overlay else None
            into = now - self.scan_from
            return {
                "screen": self.screen,
                "overlay": self.overlay,
                "path": [n["label"] for n in self.stack[1:]] + ([self.leaf["label"]] if self.leaf else []),
                "tiles": [{"label": t["label"], "more": "children" in t, "guess": bool(t.get("guess") or t.get("exact"))}
                          for t in tiles],
                "lit": lit,
                "mode": "scan" if self.scan_s else "glance",
                # scan only: seconds until the highlight moves, for the page's progress bar
                "next_s": (self.scan_s - into if into < 0 else self.scan_s - into % self.scan_s)
                if lit is not None and self.scan_s else None,
                "scan_s": self.scan_s,
                "finding": self.screen == "options" and self.options is None,
                "heard": self.heard_text,
                "thinking": self.screen == "replies" and self.reply is not None and self.replies is None,
                "plain": self.leaf and self.leaf["phrase"],
                "sentence": self.sentence,
                "action": self.leaf and self.leaf.get("action", "speak"),
                "to": self.leaf and self.leaf.get("to"),
                "can_back": self.screen != "menu" or len(self.stack) > 1,
                "left_s": max(0.0, self.deadline - now) if self.overlay else None,
                "said": self.said,
                "alert": self.alert,
                "notice": self.notice,
                "took": self.took,
                "agent": {k: self.question[k] for k in ("kind", "title", "detail")} if self.screen == "agent" else None,
                "brake": now < self.brake_until,
                # mind reader: seconds until the guessed sentence on screen says itself
                "talk_s": max(0.0, self.talk_at - now) if self.talk_at is not None and not self.overlay else None,
                "talk_total": TALK_S,
                # autopilot: seconds until Alpha does its guess, and the whole countdown, for the page's ring
                "auto_s": max(0.0, self.auto_at - now) if self.auto_at is not None and self.screen == "agent" else None,
                "auto_total": AUTO_S[self.question["kind"]] if self.auto_at is not None and self.question else None,
                "ledger": list(self.ledger),
                "counts": dict(self.counts),
            }
