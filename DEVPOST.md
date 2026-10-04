# Devpost draft — rein. (Dublin Hacx 2026)

## Inspiration

AI agents can now do real work — write code, run commands, change files. But every agent framework still assumes you have hands: to hit approve, to hit stop, to grab the keyboard when it goes wrong. For people with ALS, spinal cord injury, or cerebral palsy, that assumption locks them out of the most powerful tool of the decade.

We built the missing piece: a brake pedal for AI agents, operated entirely without hands.

## What it does

rein. is a headband remote control for AI agents. A Muse 2 EEG headband (plus a webcam) supervises Claude Code through three body signals:

- **Silence means yes.** Safe steps run after a visible ~6-second countdown. Doing nothing is approval — the agent keeps flowing.
- **Eyes closed means stop.** Two independent brakes fire: brain alpha waves behind the ears, and the webcam watching eyelid openness. A closure denies a pending permission, stops the agent before its next tool call, and holds for up to 120 seconds.
- **Bite down means approve.** A jaw clench held for a full second approves a risky step — a commit, a delete, anything outside the project — through a full-screen gate. Short bites are refused. Nothing dangerous happens without a bite.

Risk is default-deny. The system never guesses "yes" for a dangerous action.

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
- Venue Wi-Fi/DNS was hostile (our custom domain didn't resolve), so everything runs on a local-only server.
- We refused to fake results: every number in this write-up is measured, and everything unverified is labeled as such.

## Accomplishments that we're proud of

- A real, working brake on a real AI agent — not a mockup. Close your eyes and Claude Code actually stops.
- A default-deny safety architecture where a missed signal can never permit irreversible work.
- Calibration that says "no" to bad data instead of silently degrading.

## What we learned

Biosignals are honest in a way software isn't: you can't argue with a noisy electrode. Designing for the failure case — missed brake, false bite — shaped the entire architecture. Default-deny isn't a feature; it's the only sane posture when your input device is a human body.

## What's next

Testing with the actual intended users (we've only tested on ourselves so far), a per-boot auth token for the local API, named calibration profiles, and longer battery-life streaming.

## Built with

Python (FastAPI), React, Muse 2, Claude Code, Anthropic Haiku, ElevenLabs, Eyedid/SeeSo, Electron. Accuracy recipe credit: the Clench project.

---

**Honest limits (for the judges):** This is a prototype for assistive-input research, not a medical device. It does not read thoughts — it reads one brain state (eyes open vs closed) plus jaw muscle activity. Tested on the builder's head only, so far.
