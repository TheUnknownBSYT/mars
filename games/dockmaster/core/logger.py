"""
CSV storage for DOCKMASTER.
  data/sessions.csv  one row per shift
  data/events.csv    one row per action (click / pick / beam round)
data_source: prototype_gameplay | simulated. Practice is never saved.
"""
import csv
import random
from datetime import datetime, timedelta

import config as C

SESSION_COLUMNS = [
    "astronaut", "session_index", "timestamp", "local_hour", "task_version", "data_source", "invalid", "input_device",
    "sleep_hours", "fatigue", "stress", "mood",
    "t1_order_acc", "t1_perfect_rounds", "t1_rounds", "t1_timeouts", "t1_first_click_ms", "t1_click_time_ms", "t1_click_err_px", "t1_empty_clicks",
    "t2_correct", "t2_accuracy", "t2_perfect_rounds", "t2_rounds", "t2_select_time_ms", "t2_click_err_px", "t2_timeouts",
    "t3_track_err_px", "t3_on_target_pct", "t3_count_err", "t3_count_correct", "t3_rounds", "t3_answer_ms",
    "hand_eye", "memory", "attention", "status", "confidence", "baseline_mode",
]
EVENT_COLUMNS = [
    "astronaut", "session_index", "data_source", "task", "kind", "round", "expected", "clicked", "correct", "first",
    "dt_ms", "err_px", "perfect", "timeout", "first_click_ms", "time_ms", "n_correct", "n_targets",
    "track_err_px", "on_target_pct", "greens", "answer", "count_err", "answer_ms", "timestamp",
]


def _append(path, cols, rows):
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else (round(r[k], 3) if isinstance(r[k], float) else r[k])) for k in cols})


def load_history(astronaut):
    if not C.SESSIONS_CSV.exists():
        return []
    with open(C.SESSIONS_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("astronaut") == astronaut]
    return sorted(rows, key=lambda r: int(float(r.get("session_index") or 0)))


def next_index(astronaut):
    h = load_history(astronaut)
    return max(int(float(r["session_index"])) for r in h) + 1 if h else 1


def save_session(row):
    _append(C.SESSIONS_CSV, SESSION_COLUMNS, [row])


def save_events(astronaut, idx, source, events):
    _append(C.EVENTS_CSV, EVENT_COLUMNS, [{**e, "astronaut": astronaut, "session_index": idx, "data_source": source} for e in events])


def clear(astronaut):
    for path, cols in ((C.SESSIONS_CSV, SESSION_COLUMNS), (C.EVENTS_CSV, EVENT_COLUMNS)):
        if path.exists():
            with open(path, newline="", encoding="utf-8") as f:
                keep = [r for r in csv.DictReader(f) if r.get("astronaut") != astronaut]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(keep)


def make_demo_history(astronaut, n=8, seed=None):
    """n SIMULATED shifts (data_source=simulated) with a realistic learning curve."""
    rng = random.Random(seed)
    clear(astronaut)
    start = datetime.now() - timedelta(days=n + 1)
    for i in range(1, n + 1):
        L = max(0, 4 - i)
        green_err = rng.choice([0, 0, 0, 1])
        row = {
            "astronaut": astronaut, "session_index": i,
            "timestamp": (start + timedelta(days=i)).replace(hour=8, minute=30).isoformat(timespec="seconds"),
            "local_hour": 8, "task_version": C.TASK_VERSION, "data_source": "simulated", "invalid": 0, "input_device": "mouse",
            "sleep_hours": round(rng.uniform(6.5, 8), 1), "fatigue": rng.randint(2, 3), "stress": rng.randint(1, 3), "mood": rng.randint(4, 5),
            "t1_order_acc": round(min(1, 0.92 - L * 0.04 + rng.uniform(-0.03, 0.04)), 3), "t1_perfect_rounds": rng.randint(3, 5),
            "t1_rounds": C.T1_ROUNDS, "t1_timeouts": 0, "t1_first_click_ms": round(900 + L * 150 + rng.uniform(-100, 100)),
            "t1_click_time_ms": round(560 + L * 60 + rng.uniform(-50, 50)), "t1_click_err_px": round(7 + L + rng.uniform(-1.5, 1.5), 1),
            "t1_empty_clicks": rng.randint(0, 1),
            "t2_correct": 0, "t2_accuracy": round(min(1, 0.85 - L * 0.05 + rng.uniform(-0.06, 0.06)), 3), "t2_perfect_rounds": rng.randint(2, 4),
            "t2_rounds": C.T2_ROUNDS, "t2_select_time_ms": round(1500 + L * 200 + rng.uniform(-200, 200)),
            "t2_click_err_px": round(8 + rng.uniform(-2, 2), 1), "t2_timeouts": 0,
            "t3_track_err_px": round(18 + L * 2 + rng.uniform(-2, 2), 1), "t3_on_target_pct": round(78 - L * 4 + rng.uniform(-4, 4), 1),
            "t3_count_err": green_err, "t3_count_correct": C.T3_ROUNDS - min(green_err, C.T3_ROUNDS), "t3_rounds": C.T3_ROUNDS,
            "t3_answer_ms": round(2200 + rng.uniform(-300, 300)),
            "hand_eye": "normal", "memory": "normal", "attention": "normal", "status": "GO", "confidence": "n/a", "baseline_mode": "simulated",
        }
        row["t2_correct"] = round(row["t2_accuracy"] * C.T2_ROUNDS * C.T2_TAGGED)
        save_session(row)
    return n
