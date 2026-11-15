# ORBIT OPS: Mission Pulse reaction-time game (Python)

A ~4-minute daily space game with 3 reaction-time rounds. It compares each player
with their **own** normal and gives a **GO / CAUTION / NO-GO / RETEST** readiness
decision with a confidence level.

## Setup & run
```bash
pip install -r requirements.txt      # installs pygame-ce
python main.py                       # start the game
python main.py --demo AST-01         # load 8 SIMULATED sessions first (for demos)
```
Keys: **F11** fullscreen, **M** mute, **ESC** pause/back. On the check-in screen, **F2** loads demo history and **F3** clears history.

## The 3 rounds
| Round | Task | Keys | Measures |
|---|---|---|---|
| 1 Master Alarm | Alarm lights up at a random moment (1–4 s), so press fast | SPACE | Alertness: median RT, speed 1/RT, lapses ≥355 ms, false starts <100 ms, fastest/slowest 10%, time-on-task slowing (NASA PVT-B rules) |
| 2 Debris Watch | Debris = fire, satellite = hold fire (go/no-go) | SPACE | Decision: go-RT, **decision time = R2 − R1**, friendly-fire errors |
| 3 Mission Control Orders | Sort by SHAPE or COLOR; the rule switches every 3–5 trials | F / J | Adaptation: **switch cost = switch RT − repeat RT**, old-rule errors |

Each session runs: check-in (sleep, fatigue, stress, mood), then briefing + optional practice (P), then the round and a 5 s rest, three times over, then a mood check, docking, and the debrief.

## Data (folder `data/`)
- `sessions.csv`: one row per session. It includes **`reaction_ms`** (= Round 1 median), the same column name as your simulated crew data, so it plugs into Baseline 1/2.
- `trials.csv`: one row per response (rt_ms, response, correct, condition, rule…).
- Every row has `data_source` = `prototype_gameplay` or `simulated`. Practice runs are never saved.

## Decision rules (all in `config.py`)
- Sessions 1–3 are **familiarisation** (practice effect) and are left out of the baseline.
- Personal baseline = median ± robust SD (MAD) of the last ≤10 valid sessions after familiarisation.
- A component is "slower" when z > 2 (switch cost z > 2.5) vs your normal. Until you have a baseline, generic thresholds are used.
- **NO-GO** = a component is slower **and** (sleep < 6 h or fatigue ≥ 5). **CAUTION** = only one of the two. **RETEST** = data-quality failure.
- Confidence: HIGH (≥5 baseline sessions), MEDIUM (3–4), LOW (generic/familiarisation/bad data).

## Timing notes (keep these if you edit)
- Rounds poll the keyboard ~1000×/s (`tick_busy_loop`). Stimulus onset is stamped right after `display.flip()`.
- Sounds play only **after** a response, so RT stays purely visual, like NASA's PVT.
- Use the same computer, keyboard and screen every day. Absolute ms differ between devices, but personal baselines cancel that out.
- Prototype only: not validated and not equivalent to NASA's Reaction Self Test.

## Project layout
```
main.py            app loop + timing
config.py          ALL settings (trials, waits, thresholds)
core/              pure-Python logic (no pygame) - schedule, scoring, readiness, logger, progression
game/              pygame screens: rounds.py, screens.py, gfx.py (procedural art), audio.py (synth sounds)
tests/             test_core.py (unit tests), smoke_test.py (bot plays 2 full sessions headless)
```
Run tests: `python tests/test_core.py` and `python tests/smoke_test.py`
