"""
Saves data to CSV so it can go straight into the Mission Pulse baseline code.

data/trials.csv    one row per response
data/sessions.csv  one row per session (includes `reaction_ms`, same name as
                   the simulated crew data)

Every row has a `data_source` column:
    prototype_gameplay  real people playing this game
    simulated           generated demo data (never mix up with real data!)
Practice sessions are NOT saved.
"""
import csv
import random
from datetime import datetime, timedelta

import config as C

SESSION_COLUMNS = [
    "astronaut", "session_index", "timestamp", "local_hour", "task_version", "data_source", "invalid",
    "sleep_hours", "fatigue", "stress", "mood_pre", "mood_post",
    "reaction_ms",
    "r1_median_ms", "r1_mean_ms", "r1_sd_ms", "r1_speed", "r1_fast10_ms", "r1_slow10_ms",
    "r1_lapses", "r1_misses", "r1_false_starts", "r1_time_on_task_ms", "r1_valid",
    "r2_go_rt_ms", "r2_hits", "r2_misses", "r2_false_alarms", "r2_correct_holds", "r2_false_starts", "r2_accuracy",
    "decision_time_ms",
    "r3_switch_rt_ms", "r3_repeat_rt_ms", "switch_cost_ms", "r3_accuracy", "r3_switch_accuracy",
    "r3_old_rule_errors", "r3_errors", "r3_timeouts",
    "alertness", "decision", "adaptation",
    "status", "confidence", "baseline_mode",
]

TRIAL_COLUMNS = [
    "astronaut", "session_index", "data_source", "round", "trial", "condition", "rule", "is_switch",
    "congruent", "stimulus", "response", "key", "correct", "rt_ms", "lapse", "isi_s", "timestamp",
]


def _ensure_dir():
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)


def _append(path, columns, rows):
    _ensure_dir()
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})


def load_history(astronaut):
    """All saved sessions for one astronaut, oldest first."""
    if not C.SESSIONS_CSV.exists():
        return []
    with open(C.SESSIONS_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("astronaut") == astronaut]
    rows.sort(key=lambda r: int(float(r.get("session_index") or 0)))
    return rows


def next_session_index(astronaut):
    h = load_history(astronaut)
    return (max(int(float(r["session_index"])) for r in h) + 1) if h else 1


def save_session(row):
    _append(C.SESSIONS_CSV, SESSION_COLUMNS, [row])


def save_trials(astronaut, session_index, data_source, trials):
    rows = []
    for t in trials:
        r = dict(t)
        r.update(astronaut=astronaut, session_index=session_index, data_source=data_source)
        if r.get("rt_ms") is not None:
            r["rt_ms"] = round(r["rt_ms"], 1)
        if r.get("isi_s") is not None:
            r["isi_s"] = round(r["isi_s"], 3)
        rows.append(r)
    _append(C.TRIALS_CSV, TRIAL_COLUMNS, rows)


def clear_astronaut(astronaut):
    """Remove one astronaut's rows from both CSVs."""
    for path, cols in ((C.SESSIONS_CSV, SESSION_COLUMNS), (C.TRIALS_CSV, TRIAL_COLUMNS)):
        if not path.exists():
            continue
        with open(path, newline="", encoding="utf-8") as f:
            keep = [r for r in csv.DictReader(f) if r.get("astronaut") != astronaut]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(keep)


def make_demo_history(astronaut, n=8, seed=None):
    """Create n SIMULATED sessions (clearly tagged) so judges can see the baseline working.

    Early sessions are slower on purpose (practice effect).
    Replaces any existing history for this astronaut.
    """
    rng = random.Random(seed)
    clear_astronaut(astronaut)
    start = datetime.now() - timedelta(days=n + 1)
    for i in range(1, n + 1):
        learn = max(0, 4 - i) * 15                      # practice effect
        r1 = round(285 + learn + rng.uniform(-12, 12))
        go = round(r1 + 120 + learn + rng.uniform(-20, 20))
        rep = round(640 + rng.uniform(-30, 30))
        cost = round(160 + rng.uniform(-30, 30))
        row = {
            "astronaut": astronaut, "session_index": i,
            "timestamp": (start + timedelta(days=i)).replace(hour=8, minute=30).isoformat(timespec="seconds"),
            "local_hour": 8, "task_version": C.TASK_VERSION, "data_source": "simulated", "invalid": 0,
            "sleep_hours": round(rng.uniform(6.5, 8.0), 1), "fatigue": rng.randint(2, 3),
            "stress": rng.randint(1, 3), "mood_pre": rng.randint(3, 4), "mood_post": rng.randint(3, 5),
            "reaction_ms": r1, "r1_median_ms": r1, "r1_mean_ms": r1 + rng.randint(5, 15),
            "r1_sd_ms": rng.randint(28, 45), "r1_speed": round(1000 / (r1 + 8), 3),
            "r1_fast10_ms": r1 - 50, "r1_slow10_ms": r1 + 90,
            "r1_lapses": rng.randint(0, 2), "r1_misses": 0, "r1_false_starts": rng.randint(0, 1),
            "r1_time_on_task_ms": rng.randint(-10, 20), "r1_valid": 30,
            "r2_go_rt_ms": go, "r2_hits": rng.randint(17, 18), "r2_misses": rng.randint(0, 1),
            "r2_false_alarms": rng.randint(0, 1), "r2_correct_holds": rng.randint(6, 7), "r2_false_starts": 0,
            "r2_accuracy": round(rng.uniform(0.92, 1.0), 3), "decision_time_ms": go - r1,
            "r3_switch_rt_ms": rep + cost, "r3_repeat_rt_ms": rep, "switch_cost_ms": cost,
            "r3_accuracy": round(rng.uniform(0.88, 1.0), 3), "r3_switch_accuracy": round(rng.uniform(0.8, 1.0), 3),
            "r3_old_rule_errors": rng.randint(0, 1), "r3_errors": rng.randint(0, 2), "r3_timeouts": 0,
            "alertness": "normal", "decision": "normal", "adaptation": "normal",
            "status": "GO", "confidence": "n/a", "baseline_mode": "simulated",
        }
        save_session(row)
    return n
