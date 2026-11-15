# Mission Pulse: baseline code

Three personal baselines per astronaut and per signal, every variant we considered, a benchmark that picks the best one, and a replay of your three real NASA radiation files.

Body-signal results come from a **simulated** crew, because no public astronaut wearable data exists. Say so in the pitch. Radiation results come from **real** RadLab data.

---

## Files

| File | What it does |
|---|---|
| `baselines.py` | The engine. Pre-launch (flat), post-launch (locked) and recent (rolling) baselines, scores, the five lights, drift detection, multi-signal agreement, and the ship-or-person check |
| `simulator.py` | A fake but realistic crew: 4 astronauts, 270 days, 8 signals, with labelled events (illness, slow drift, solar storm nights, one-day blips, broken sensors) |
| `benchmark.py` | Tries about 250 variants on simulated crews, picks the best within an alarm budget, then re-tests it on **new** crews |
| `radiation_replay.py` | Runs your three RadLab CSVs through a danger watch (hours) and a trend watch (days); writes plots and calibration numbers |
| `pipeline.py` | What the app calls: daily table in, lights plus plain-English reasons out |
| `wesad_effects.py` | Run on Kaggle with WESAD attached. Measures real calm-vs-stress changes to size the simulator's events |
| `data/` | Your three radiation files (renamed) |
| `plot_tradeoff.py` | One chart for the pitch: false alarms vs illnesses caught, for every variant |
| `results/` | Everything the scripts write (tables, configs, plots) |

## Run it

```bash
pip install pandas numpy scipy matplotlib
python benchmark.py --quick     # 15-second check that everything works
python benchmark.py             # full run, about 5 minutes on 2 CPU cores
python radiation_replay.py      # a few seconds
python pipeline.py              # demo: lights for a simulated crew -> results/demo_lights.csv
python plot_tradeoff.py         # results/tradeoff.png
```

On Kaggle, upload the folder as a dataset (or paste the files into a notebook) and run the same commands with `!python ...`.

---

## How it works, in one screen

**Three baselines** (per astronaut, per signal):

1. **Pre-launch (flat):** Earth normal from the pre-launch days. It never changes.
2. **Post-launch (locked):** space normal, learned on mission days 15–30 and then frozen. Days 0–14 are "settling in": any change then shows **blue** instead of raising an alarm.
3. **Recent (rolling):** the last week or so. It keeps moving, and days that are already flagged don't update it.

**Score** = (today − baseline) ÷ usual wobble. A score of 3 means "3 usual wobbles away".

**Lights:**
- **Green:** normal.
- **Yellow:** off for several days.
- **Red:** far off.
- **Grey:** missing, impossible, or a flatlined sensor.
- **Blue:** changed, but explained (settling in, or the whole crew moved together, which points to the ship).

**Two layers:**
- **Trend watch (days)** for baselines and lights.
- **Danger watch (hours)** for things that can't wait for a daily summary. Here it runs on radiation; for body signals it needs the hard medical limits from your notes.

---

## What the benchmark found

The "labels" are the events we injected into the simulated crews, so we know the right answer for every day. Each variant was tuned on 10 crews and then re-checked on 10 **different** crews. Numbers below are from the new crews.

| | Illnesses caught | Days to catch | Slow drifts caught | Days to catch drift | False-alarm days per astronaut per month |
|---|---|---|---|---|---|
| **STRICT (default)** | 63% | 1.2 | 68% | 37 | **0.5** |
| **BALANCED (sensitive mode)** | 84% | 1.2 | 78% | 31 | **1.2** |
| Naive (alarm whenever score > 2.5) | 100% | 0.4 | 100% | 11 | **14.3** |

The naive version "catches everything", but it raises an alarm on about half of all days and on 78% of harmless one-day blips. Nobody would keep it switched on. That is the alarm-fatigue argument, made with numbers.

**The winning recipe (STRICT):**

- **Fixed baselines:** median and MAD blended with a population prior (`shrink`). It had the fewest false alarms, especially with only 5 pre-launch days.
- **Main detector:** today vs space normal, flagged when the score is past **3** on **3 of the last 5 days**.
- **Multi-signal agreement:** if **4 or more signals** are past **2.5** on the same day, those signals go yellow. This one change lifted illness catch rate from 46% to 68% in tuning without breaking the budget, because illness moves many signals at once and random noise doesn't.
- **BALANCED** adds: a looser main rule (score past 3 on **2 of the last 3** days) and agreement from **3** signals instead of 4. It catches about a third more illnesses for about 0.7 more false-alarm days per astronaut per month.

**Things that lost, and why** (worth one line in the Q&A):

- **Rolling-baseline detectors** were worse than comparing against the locked space normal. A rolling baseline slowly gets used to whatever is going on.
- **CUSUM drift detection** produced 1.6–15 false-alarm days a month and never fit the 1-per-month budget. It is very sensitive to small errors in the post-launch baseline, which is only estimated from about 15 days.
- **Plain median/MAD** had 3–7× more false alarms than the blended version. A MAD estimated from 5–20 days is too noisy.
- **The EWMA control chart** caught everything, but at 11–26 false-alarm days a month.

Full tables are in `results/stage*.csv`, and the chosen settings in `results/best_config.json` and `results/balanced_config.json`.

---

## Radiation replay (real data)

| Environment | Days | Typical daily median | Day-to-day wobble | What happened |
|---|---|---|---|---|
| Mars cruise (Liulin-MO, 2016) | 90 | 15.4 | 0.20 | All green. There is a slow **~27-day ripple** (the Sun's rotation modulating cosmic rays), which is normal, not an alarm |
| Moon trip (Artemis I HERA, 2022) | 26 | 16.6 | 0.11 | Danger watch fires on **launch day (Nov 16)**, the radiation-belt passage, with a peak reading of about 8,000. Every other day is green |
| ISS (Lidal, 2020–23) | 1,151 | 3.7 | 0.15 | Several **step changes** (about 3.6 → 5.4 → 3.6). The pattern looks more like an instrument or location change than space weather. Check the Lidal Knowledgebase page before claiming anything |

Plots are `results/radiation_*.png`. Use `results/radiation_calibration.csv` to set the simulator's radiation level and wobble for each environment.

**Lesson from the radiation data:** with a fixed baseline, the 27-day ripple raised false alarms (23 yellow and 11 red days on a quiet cruise). Radiation needs a **rolling 4-week reference** plus re-baselining after a lasting step. Body signals need the **locked space normal**.

---

## Cautions (read before you pitch)

1. **The body-signal results are only as true as the simulator.** Every effect size and wobble in `simulator.py` is an illustrative assumption. The numbers show the method works and how the variants compare; they are not real-world accuracy. Also, we picked "slow signals" (vision, HRV, sleep, reaction) for drift partly because that is where the simulator puts drift. Defend that choice with real risks: vision changes (SANS) and cardiovascular deconditioning.
2. **No peeking at the future.** The baseline for day *t* only uses days before *t*. If you ever use a centred rolling window or fit on the whole series, the results will look great and mean nothing.
3. **Tune on some crews and report on others.** Numbers shift between tuning and test crews (STRICT illness catch rate: 68% → 63%). That is normal, and it is why we report test-crew numbers.
4. **Small samples lie.** 15 post-launch days give a rough estimate of "space normal". That error is what blew up CUSUM. If you can afford it, a longer window (15–45) is steadier.
5. **The frozen-baseline trap.** If flagged days never update the baseline, a permanent change raises an alarm forever. This is why `rebaseline_after` exists. In the app, add an "accept as my new normal" button that a crew member or the medical officer must press.
6. **More signals means more false alarms.** 8 signals × 4 astronauts × 270 days gives a lot of chances to be wrong. Count the alarm budget per astronaut, not per signal.
7. **Missing is not normal.** Missing, impossible or flatlined data turns grey and never enters a baseline.
8. **A daily summary hides emergencies.** The danger layer (hours or minutes) is separate. Its hard limits (very low SpO2, extreme heart rate and so on) must come from a medical reference, not from this benchmark.
9. **Radiation units and meaning.** The RadLab column has no unit in the file, so check each instrument's Knowledgebase page. Instrument dose rate is **not** astronaut effective dose (mSv). Any conversion is a labelled assumption.
10. **Risk status, not diagnosis.** Use "astronauts", not "patients". Lights say "off from your normal", never "you have X".
11. **WESAD gives stress effect sizes, not daily wobble.** Each subject was recorded for about 2 hours. Use it to size events (how much heart rate jumps under stress), not day-to-day noise.

## Tips to improve (if you have time)

- **Real effect sizes:** run `wesad_effects.py` on Kaggle and put the stress-vs-calm numbers into `STORM_PATTERN` / `ILLNESS_PATTERN`.
- **Real storm dates:** in a browser, open
  `https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/SEP?startDate=2020-01-01&endDate=2023-04-30`
  and save the page as `donki_sep.json`. If it redirects, use the new address it shows. Then run `python radiation_replay.py --donki donki_sep.json`. Storm dates appear on the plots, and the report counts how many storms the danger watch caught.
- **Let the crew pick sensitivity:** STRICT by default, BALANCED after a storm or when someone feels off. Both configs are saved.
- **Per-signal thresholds:** vision might deserve a stricter setting than mood.
- **Schedule-aware blue:** feed planned spacewalks and exercise into the "explained change" rule.
- **Second opinion:** an Isolation Forest over all signals can nudge a light, but it should never decide one on its own.
- **Show uncertainty:** the reasons in `pipeline.py` already say how far off a value is. Add "baseline still learning" when it has few days.

**Hackathon rules:** if the 2026 rules still say no project code before Saturday 11:00, treat this as reference material and rebuild or adapt it during the event, or check with the organisers first.
