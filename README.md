# Mission Pulse

**Astronaut health monitoring that learns each crew member's own normal and tells you when the ship can be trusted to watch them without Earth.**

NASA Space Apps Challenge 2026 · Mohali local event · Challenge: *Create Health Monitoring Software for Astronauts on Space Missions*

Live app: https://claude.ai/artifact/HTAnv9Zk9vjH5cxREmEBsB (the owner must share it before others can open it)

---

## The idea in 30 seconds

- **Three personal baselines per astronaut and signal.**
  - **Earth normal:** pre-launch days.
  - **Space normal:** learned in flight from day 15, then locked once stable.
  - **Recent:** the last 7 days, never including today.

  Comparing them separates normal space adaptation from a sudden change (for example illness) and from a slow decline (for example vision changes from SANS).
- **Five lights:** OK (green), Watch (yellow), Act (red), Learning (blue, compared with the Earth normal while the space normal is learned) and No data (grey, a sensor problem). The app says "I don't know" instead of guessing.
- **Handover rule (Focus 2).** Each astronaut's onboard model is ready once every signal's space normal has locked. That has to happen before the one-way signal delay to Earth passes 5 minutes (day 152 of a minimum-energy Mars transfer). In the demo crew, everyone is ready by day 64, an 88-day margin.
- **Builds on NASA's EIMO** (Earth Independent Medical Operations): it doesn't claim offline medicine is new. It adds a measurable rule for *when* the onboard model can be trusted.
- **Daily inputs need no typing:**
  - Wearable sensors give resting heart rate, HRV, breathing, skin temperature and sleep.
  - Four short games give reaction time, faint vision, hand-eye control and hearing in noise.
  - A mood check-in gives mood.

---

## What's in this folder

| Folder | What it is | How to run |
|---|---|---|
| `app/mission_pulse.html` | **The app.** One file, works offline. Daily check-in, 4 playable games, monitor with the 5 lights, crew view, ship conditions, handover readiness, CSV export, import of Kaggle and game results. | Double-click to open in Chrome or Edge (its own tab, not a preview, so data stays after reloading). |
| `app/source/` | Readable source of the two main parts inside the app: `engine.js` (the three baselines, lights, handover; same logic as the Python) and `games.js` (Orbit Ops, Starsight and Dockmaster for the browser). | For reading; already built into the HTML. |
| `kaggle/` | The analysis code: `baseline1_prelaunch.py`, `baseline2_space_normal.py`, `baseline3_recent.py`, `focus2_handover.py`, plus `wesad_priors.py` (starting values from WESAD). | Kaggle notebook, internet off, CPU only. One cell per file, in this order, then Run all. |
| `kaggle/outputs/` | Results of the latest run: baselines, the compared table, handover summary and chart. | Import `baselines_all_three_compared.csv` and `handover_summary.csv` into the app with **Import Kaggle results**. |
| `games/` | The four games as standalone programs: `orbit_ops` (reaction), `starsight` (vision), `dockmaster` (hand-eye and memory), `commscheck` (hearing in noise, needs headphones). Starsight and Comms Check also have a single-file browser version (`.html`). | See "Run the games" below. |
| `data/radiation_radlab/` | Real radiation dose-rate data: Liulin-MO (Mars cruise), Artemis I HERA (Orion) and ISS Lidal. | Used by `research/benchmark/radiation_replay.py`. |
| `data/demo/` | The app's simulated demo crew (mission and pre-launch), in the same columns as the Kaggle code. | Upload to Kaggle and set `MISSION_CSV` / `PRELAUNCH_CSV` to rerun the notebooks on it. |
| `research/benchmark/` | The earlier benchmark that chose the settings: detector comparisons, alarm budget, multi-signal agreement, radiation replay. Results are in `results/`. | `python benchmark.py`, `python radiation_replay.py` |

---

## Run it

**App:** open `app/mission_pulse.html`.
- To see everything at once, turn on **Demo preview** (5 simulated astronauts with planted events).
- For real use, keep Demo preview off and click **Check-in**. The steps are: Save and continue → answer 3 questions → Game 1 → 2 → 3 → 4 → monitor.
- **Sync next 7 days** fast-forwards the simulated sensors.

**Kaggle:**
1. Create a notebook and set internet off and accelerator to none.
2. Paste the four `kaggle/*.py` files as cells 1 to 4, in order.
3. Click Run all.
4. Outputs appear in `/kaggle/working`.

With no inputs the notebooks use their own simulated crew. To use real data, set `MISSION_CSV` and `PRELAUNCH_CSV`.

**Games (standalone):**
```bash
pip install pygame-ce numpy        # Orbit Ops and Dockmaster
cd games/orbit_ops  && python main.py
cd games/dockmaster && python main.py
pip install pygame numpy           # Starsight and Comms Check (or open their .html files in Chrome)
cd games/starsight  && python starsight_app.py --windowed
cd games/commscheck && python comms_app.py --windowed
```
`pygame` and `pygame-ce` can't be installed side by side. Use two virtual environments, or just open the `.html` versions. Inside the app, all four games are already built in.

---

## How the parts connect

```
wearable sensors (simulated) ─┐
Game 1 Orbit Ops    → reaction time ─┤
Game 2 Starsight    → faint vision   ├─► app record per astronaut per day ─► 3 baselines ─► 5 lights + handover readiness
Game 3 Dockmaster   → hand-eye error ─┤                    │
Game 4 Comms Check  → hearing in noise┤                    ├─► Export CSV ─► Kaggle notebooks ─► Import Kaggle results (checks agreement)
mood check-in       → mood ──────────┘                    └─► Ship conditions (cabin CO₂, noise…) shown next to crew changes
```

- **The app and the Kaggle notebooks run the same model.** On the same data they agree on 100% of flags (25,600 of 25,600 lock, drift, sudden and blip flags).
- **Each game keeps its own verdict** (GO, CAUTION, NO-GO, RETEST, SCAN NOW, GLASSES, HEARING CHECK) and also feeds one number into the baselines. Familiarisation and RETEST sessions are kept out of the baselines.

---

## Key results (simulated crew)

- **Handover-ready:** A1 on day 56, A2 on 59, A3 on 60, A4 on 64. The deadline is day 152 (one-way delay over 5 minutes).
- **Slow vision decline caught:** day 142 for A1 and day 158 for A3.
- **Sudden events flagged:** A2's illness on days 36 to 39 and A3's sleep crash on days 122 to 123. A single bad night stays Watch, not Act.
- **Sensor faults:** shown grey, not as alarms.

---

## Data and sources

- **Radiation:** RadLab data (Liulin-MO / ExoMars TGO 2016, Artemis I HERA-HSU1 2022, ISS Lidal 2020–23). The instrument dose is not the dose a crew member receives.
- **WESAD** (wearable stress and affect dataset, 15 subjects, Kaggle mirror: orvile/wesad-wearable-stress-affect-detection-dataset). It provided the starting values for resting heart rate, HRV, breathing and skin temperature, and showed heart rate rising by about 22 bpm under stress in all 15 subjects. The dataset itself is **not** included; get it from its source.
- **Other settings are stated assumptions:**
  - typical values for sleep, reaction time, faint vision (logCS), mood, hand-eye and hearing;
  - the 5-minute handover cutoff;
  - the simplified Mars orbit (circular orbits, minimum-energy transfer).
- **Background:** NASA EIMO, NASA's Cognition test battery, VR use on the ISS (Grasp, Vection, VR Mental Care, a VR vision test for SANS), Artemis II health research (ARCHeR), NASA-STD-3001 CO₂ limits.

## Limitations

- The crew data is **simulated**: sensor readings and planted events.
- The games are screening prototypes: not validated, not medical devices, and not equivalent to NASA's tests.
- The lights describe change from each person's own normal. They are not a diagnosis.

## Sharing this project

- **Code and files:** put this folder in a public **GitHub** repository; Space Apps asks for a project link. Every file is under GitHub's 25 MB browser-upload limit (the largest, `data/radiation_radlab/iss_lidal.csv`, is about 23 MB), so you can drag the whole folder in.
- **The app:** share the claude.ai link from its page (Share), or host `app/mission_pulse.html` on GitHub Pages so anyone can open it in a browser.
- **The notebooks:** make the Kaggle notebook public and link it here.
