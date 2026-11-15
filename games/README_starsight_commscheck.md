# Mission Pulse games

Two short screening games for the Mission Pulse astronaut health project.
Screening and education prototypes only: not medical devices, not validated.

## Setup (once)

    pip install pygame numpy

## COMMS CHECK (hearing in noise, about 2.5 min, headphones)

    cd commscheck
    python comms_app.py --windowed

- `comms_core.py`  scoring, staircase, decisions (GO / CHECK / HEARING CHECK / RETEST)
- `comms_app.py`   the game screens (run this one)
- `comms_voice/`   the ten spoken digits, 0.wav to 9.wav. Keep this folder next to the .py files.
                   To use a real voice, replace these files with your own recordings.
- `commscheck.html`  the same game for the browser, one file. Open it in Chrome.
                   It can also record a real voice and export it as 0.wav to 9.wav.
- Creates `commscheck_history.json` and `commscheck_scans.csv` when you save a scan.

## STARSIGHT (vision, about 2.5 min)

    cd starsight
    python starsight_app.py --windowed

- `starsight_core.py`  scoring and decisions (GO / GLASSES / CHECK / SCAN NOW / RETEST)
- `starsight_app.py`   the game screens (run this one)
- `starsight.html`     the same game for the browser, one file.
- Round 1 Ghost Signals (faint vision, 50 cm). Round 2 Sharp Shooter (near vision, 40 cm).
- Creates `starsight_history.json` and `starsight_scans.csv` when you save a scan.

## Notes

- In each game the two .py files must stay in the same folder.
- Leave out `--windowed` to run full screen. ESC quits.
- The built-in digit voice is the CMU Flite "kal" voice.
