# Devpost draft — rein. (Dublin Hacx 2026)

Repo: https://github.com/NayanVangala/rein · Demo video: [demo video link]

*Started before the event as an assistive communication board; the agent-supervision layer (brake, gate, hooks, camera brake, deck) was built during Dublin Hacx.*

## Inspiration

AI agents can now do real work — write code, run commands, change files. But every agent framework still assumes you have hands: to hit approve, to hit stop, to grab the keyboard when it goes wrong. For people with ALS, spinal cord injury, or cerebral palsy, that assumption locks them out of the most powerful tool of the decade.

We built the missing piece: a brake pedal for AI agents, operated entirely without hands.

## What it does

rein. is a headband remote control for AI agents. A Muse 2 EEG headband (plus a webcam) supervises Claude Code through three body signals. Today it works with Claude Code's hooks; other agents are next.

- **Silence means yes.** Safe steps run after a visible ~6-second countdown. Doing nothing is approval — the agent keeps flowing.
- **Eyes closed means stop.** Two independent brakes fire: brain alpha waves behind the ears, and the webcam watching eyelid openness. A closure denies a pending permission, stops the agent before its next tool call, and holds for up to 120 seconds.
- **Bite down means approve.** A jaw clench held for a full second approves a risky step — a commit, a delete, anything outside the project — through a full-screen gate. Short bites are refused. Nothing dangerous happens without a bite.

Risk is default-deny. Anything not on a short safe list waits for a held bite.

## How we built it

- **Hardware:** Muse 2 headband over BLE (EEG at 256 Hz + accelerometer/gyro/PPG). We ditched BrainFlow after it hung on macOS and wrote our own streaming layer.
- **Signal processing:** Custom detectors — bite via EMG-band energy, eyes-closed via alpha-band share (not raw power, so it survives noisy foreheads), with hysteresis and personal calibration that *refuses* weak data instead of saving it.
- **The brake:** A user-scope Claude Code plugin. Its PreToolUse hook refuses every tool call while the brake is engaged. The demo money-shot: eyes close on stage, the live alpha trace crosses the threshold line, and the agent's next tool call is denied in real time.
- **The gate:** Risky steps raise a full-screen gate. Allow only lights up for a held bite; closed eyes veto and brake; keyboard works as a stand-in.
- **Webcam as second brake:** Eyedid/SeeSo eye tracking with the accuracy recipe we learned from the Clench project (One Euro filtering, sticky tiles, 300 ms dwell, 5-point calibration) — plus a fallback ladder that steps down to auto-scan if tracking is lost, so the camera brake survives.
- **Voice:** ElevenLabs narration so the wearer hears what's happening without looking.
- **Board AI:** Claude Haiku personalizes suggestions from the wearer's own recent spoken sentences.

## Challenges we ran into

- The Muse 2's forehead EEG is noisy, and eyes-closed alpha detection is probabilistic — on 109 people's public EEG data we catch ~86% of closures with a median 5.6 s delay. That delay *races* our 6-second autopilot countdown, so we built the camera brake as the fast path.
- We refused to fake results: every number in this write-up is measured, and everything unverified is labeled as such.

## Accomplishments that we're proud of

- A real brake on a real AI agent, not a mockup: when the brake fires, Claude Code's next tool call is refused. We verified that end to end. How reliably closed eyes trigger it is a separate, measured question (see Challenges).
- A default-deny safety architecture where a missed signal does not approve a risky step.
- Calibration that says "no" to bad data instead of silently degrading.

## What we learned

Biosignals are honest in a way software isn't: you can't argue with a noisy electrode. Designing for the failure case — missed brake, false bite — shaped the entire architecture. Default-deny isn't a feature; it's the only sane posture when your input device is a human body.

## What's next

Testing with the actual intended users (we've only tested on ourselves so far), a per-boot auth token for the local API, named calibration profiles, and longer battery-life streaming.

## Built with

Python (FastAPI), React, Muse 2, Claude Code, Anthropic Haiku, ElevenLabs, Eyedid/SeeSo, Electron. Accuracy recipe credit: the Clench project.

## Verified vs not yet

- **Verified on the builder's head:** bite detection, headband streaming, calibration that refuses weak data, the brake path from signal to Claude Code (a tool call was actually refused), and Haiku suggestions (about 1 s per call).
- **Measured offline on 109 people's public EEG:** 86% of eyes-closed events caught, 73% without a false brake, median delay 5.6 s.
- **Not yet verified live:** eyes-closed detection on the builder's own head (results so far are mixed), the webcam brake and gaze with real eyes, the full-screen gate with a real held bite, and the VS Code extension.

---

**Honest limits (for the judges):** This is a prototype for assistive-input research, not a medical device. It does not read thoughts — it reads one brain state (eyes open vs closed) plus jaw muscle activity. Tested on the builder's head only, so far.
