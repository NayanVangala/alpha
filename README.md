# rein. — a brake pedal for AI agents

*A headband remote control for AI agents: silence lets safe work through, eyes closed stops it, and nothing dangerous happens without a bite.*

rein. pairs a Muse 2 EEG headband (plus a webcam) with Claude Code. Three body signals supervise the agent:

- **Silence → yes.** Safe steps on a short allow-list run after a visible ~6 s countdown. Doing nothing is approval.
- **Eyes closed → stop.** Two independent brakes: brain alpha waves (Muse TP9/TP10) and the webcam (eyelid openness). A closure denies a pending permission, stops the agent before its next tool call, and holds up to 120 s or until you answer "what's next".
- **Bite down → approve.** A jaw clench held ~1 s approves a risky step (commits, deletes, anything outside the project) through a full-screen gate. Short bites are refused with "Hold the bite for a full second".

Built for people who can think but can't use their hands — ALS, spinal cord injury, cerebral palsy — and for anyone who wants an "I can stop it without touching anything" safety switch.

## Honest limits

This is a prototype for assistive-input research, **not a medical device**. What we can say with evidence:

- Eyes-closed alpha detection is probabilistic: on 109 people's public EEG data (PhysioNet), about **86% of closures caught**, median delay **~5.6 s**, 73% of sessions with no false brake.
- It does not read thoughts. It reads one brain state (eyes open vs closed) plus jaw muscle activity.
- Webcam gaze needs calibration and good light.
- Tested on the builder's own head so far — not yet on the intended users.

## Quickstart

**Requirements:** Python ≥3.12 ([uv](https://docs.astral.sh/uv/)), Node 18+, a Muse 2 headband (or use the simulator).

```bash
# 1. backend
cd ~/alpha-clean
uv sync

# 2. frontend (the server serves src/frontend/dist, which is gitignored — build it)
cd src/frontend && npm install && npm run build && cd ../..

# 3. run — real headband
uv run --env-file .env python -m src.backend.server --demo

# …or the simulator (E = eyes, Space/B = bite)
uv run --env-file .env python -m src.backend.server --demo --sim
```

Open http://localhost:8000/ for the slide deck, http://localhost:8000/board for the app.

**Claude Code plugin** (this is what makes the brake real — the PreToolUse hook refuses every tool call while eyes are closed):

```bash
claude plugin marketplace add NayanVangala/rein
claude plugin install rein@rein
```

While hacking, `REIN_BRAKE=off` in `.env` disables the brake (the server must restart to read it). **Remove that line before any demo.**

**Tests:** `uv run pytest -q` (285 passing). Frontend: `cd src/frontend && npm run build` (tsc + vite).

## How it works

```
Muse 2 (BLE/EEG) ──┐
                   ├─► detectors (signals.py) ─► gestures ─► board state machine (board.py)
Webcam (eyelids) ──┘                                                     │
                                                                        ▼
                                                     Claude Code hooks (claude_code.py)
                                                     PreToolUse refuses while brake is on
```

- `src/backend/` — FastAPI server, Muse BLE streaming, signal detectors, calibration (refuses weak data), the board state machine, the risky-step gate, Claude Code hooks with a default-deny risk classifier, ElevenLabs narration, Telegram/Twilio help alerts (dry-run by default).
- `src/frontend/` — React board, floating HUD (`?hud`), full-screen risk gate, scroll-film slide deck, eye-tracking accuracy test (`/gaze`) with the Clench accuracy recipe (One Euro filter, sticky tiles, 300 ms hold, 5-point calibration, 90% bench) and a fallback ladder (eyes → pointer → auto-scan).
- `src/claude-plugin/` — the `rein@rein` plugin (SessionStart, PreToolUse, PermissionRequest, Stop hooks).
- `scripts/` — `closure_check.py` (10 eyes-closed trials, needs ≥7/10), `check_muse.py`, `eval_physionet.py`, …

The server binds **127.0.0.1 only** — local, no auth. Post-event hardening planned: a per-boot bearer token on `/api/*`.

## Credits

- **Clench** — the prior project we borrowed the gaze-accuracy recipe from.
- **Eyedid (SeeSo)** — webcam eye-tracking SDK.
- **ElevenLabs** — voice narration.
- **Anthropic** — Claude Code and Haiku (board suggestions).

Built at Dublin Hacx 2026, SAP San Ramon.
