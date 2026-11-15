# DOCKMASTER: 3-minute hand-eye + memory check (Mission Pulse)

Three 1-minute tasks, each with **one simple rule** (about as hard as NASA's WinSCAT, but with a different concept: moving objects, clicking, tracking).

## Run
```bash
pip install -r requirements.txt     # pygame-ce
python main.py                      # start
python main.py --demo AST-01        # 8 SIMULATED shifts first (personal baseline works immediately)
```
Keys: **F11** fullscreen · **M** mute · **ESC** pause/back. On check-in, **F2** loads demo history and **F3** clears history. On briefings, **P** runs a practice round.

## The three tasks
| Task | Rule | Rounds | Time | Measures |
|---|---|---|---|---|
| **1 PORT SEQUENCE** | Click the docking ports in order 1→5 (numbers show 1.5 s, then hide) | 5 | ~50 s | memory (order accuracy) + hand-eye (click speed, click error) |
| **2 TRACK THE SATELLITE** | 2 of 6 satellites blink; they move 6 s; click the 2 that blinked | 4 | ~50 s | memory for moving objects + eye tracking |
| **3 STEADY BEAM** | Keep the laser on a drifting satellite and count the GREEN flashes (25 s) | 2 | ~60 s | hand-eye tracking + attention while busy |
| **Total** | | | **~3 min** | |

## Result
**HAND-EYE · MEMORY · ATTENTION**, each compared with the player's **own normal**. Combined with sleep and fatigue, they give **GO / CAUTION / NO-GO / RETEST** with a confidence level.
- The first 3 shifts are familiarisation, the same as NASA's WinSCAT protocol (3 orientation sessions, then baseline).
- The baseline is a rolling robust median of recent valid shifts. Only declines are flagged.
- Ports, satellite paths, beam paths and flashes are new every shift. Nothing repeats.

## Data (`data/`)
- `sessions.csv`: one row per shift (all scores + component statuses + decision + `input_device`)
- `events.csv`: one row per click / pick / beam round
- `data_source` = `prototype_gameplay` or `simulated`. Practice is never saved.

## Files
```
main.py · config.py (all settings + metric table)
core/generators.py  fresh content each shift      core/scoring.py   events -> scores
core/readiness.py   baseline + GO/NO-GO           core/logger.py    CSV + demo history
game/rounds.py      the 3 tasks                   game/screens.py   check-in, briefings, debrief
game/base.py, gfx.py, audio.py                    drawing + sounds (no asset files)
tests/test_core.py · tests/smoke_test.py (bot plays a full shift) · tests/screenshots.py
```
Prototype for research/education: not validated, and not a NASA tool.
