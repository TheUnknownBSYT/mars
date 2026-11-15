"""
Mission Pulse - Baseline 2: the SLOW ROLLING baseline ("space normal")
=====================================================================
Each astronaut's normal IN SPACE, per signal.

How it behaves
  - Days 0..14: the body is settling into weightlessness. We don't learn yet.
  - From day 15: learns from the last WINDOW good days (default 60) and keeps
    improving every day. Center = median, wobble = MAD blended with the
    typical daily wobble (so a few quiet days can't make it over-sensitive).
  - Protection against "getting used to" a problem: a day that is far from the
    current space normal (|z| > ACCEPT_Z) is NOT learned from. So a slow decline
    (e.g. vision loss) stays visible instead of quietly becoming "normal".
  - Every day it reports how STABLE it is (feeds Focus 2, the handover):
      * enough good days (MIN_DAYS_READY, default 40)
      * the center barely moved over the last 14 days (< 0.25 wobbles)
      * the wobble estimate barely moved over the last 14 days (< 20%)
    When all three hold, the signal is "ready" and the baseline LOCKS.
    It can also be forced to lock on a given day (predicted blackout); if it
    wasn't ready by then, it is flagged NOT READY (shown grey in the app).
  - After locking: every day is compared with the locked space normal, and a
    "drift" check compares the last 14 days with it (slow declines).

Kaggle: run baseline1_prelaunch.py first (same notebook or as an attached
script). With no CSV this runs a demo crew with planted events:
  settling-in shift, a 5-day illness, and a slow vision decline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:  # baseline 1 as a file next to this one
    from baseline1_prelaunch import PRIORS, clean, fit_prelaunch_baseline
except ImportError:  # baseline 1 pasted into an earlier notebook cell
    if "PRIORS" not in globals():
        raise ImportError("Run baseline1_prelaunch.py first (or put it next to this file).")

MAD_TO_SD = 1.4826

# ---- settings (all in days unless noted) ------------------------------------
START_DAY = 15         # start learning after the settling-in period
WINDOW = 60            # learn from the last N good days (try 60-90)
ACCEPT_Z = 3.0         # don't learn from days further than this from the space normal
MIN_DAYS_READY = 40    # good days needed before "ready"
STABLE_LOOKBACK = 14   # stability is judged over this many days
CENTER_TOL = 0.25      # center may move < this many wobbles over the lookback
SCALE_TOL = 0.20       # wobble estimate may change < 20% over the lookback
SHRINK_N0 = 10         # how many days the typical-wobble prior is "worth"
DRIFT_WINDOW = 14      # drift check: median of last N days vs the locked normal
DRIFT_Z = 3.0
DRIFT_PERSIST = 5      # ...beyond DRIFT_Z for this many days in a row


def _estimate(vals: np.ndarray, within_sd: float) -> tuple[float, float]:
    """Median, and MAD blended with the typical daily wobble."""
    n = len(vals)
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)) * MAD_TO_SD) if n >= 2 else within_sd
    if not np.isfinite(mad) or mad == 0:
        mad = within_sd
    w = n / (n + SHRINK_N0)
    scale = np.sqrt(w * mad ** 2 + (1 - w) * within_sd ** 2)
    return med, float(max(scale, 0.5 * within_sd))


def run_space_normal(mission_values, signal: str, force_lock_day: int | None = None,
                     protect: bool = True) -> pd.DataFrame:
    """
    mission_values : daily values for ONE astronaut and ONE signal, index = mission day 0..T-1
    force_lock_day : lock on this day even if not ready (e.g. predicted blackout)
    protect        : True = don't learn from far-off days (recommended)
    Returns one row per day.
    """
    prior = PRIORS[signal]
    within_sd = prior[2]
    x, reasons = clean(mission_values, prior[3], signal=signal)
    T = len(x)

    learned: list[float] = []
    hist_center, hist_scale = [], []
    center = scale = np.nan
    locked = False
    lock_day, lock_ready = None, None
    recent: list[float] = []
    drift_run = 0
    rows = []

    for t in range(T):
        v = x[t]
        row = dict(day=t, value=mission_values[t], grey_reason=reasons[t])

        # score today against the space normal as it stood BEFORE today
        z = (v - center) / scale if np.isfinite(v) and np.isfinite(center) else np.nan
        row["z_vs_space_normal"] = round(z, 2) if np.isfinite(z) else np.nan

        # drift check (only after lock)
        drift = False
        if np.isfinite(v):
            recent.append(v)
            recent = recent[-DRIFT_WINDOW:]
        if locked and len(recent) >= DRIFT_WINDOW // 2:
            se = 1.25 * scale * np.sqrt(1 / len(recent) + 1 / max(len(learned), 1)) * 1.3
            zd = (np.median(recent) - center) / se
            drift_run = drift_run + 1 if abs(zd) > DRIFT_Z else 0
            drift = drift_run >= DRIFT_PERSIST
        row["drift"] = drift

        # learn from today? (only before lock, after settling, good data, not far off)
        accepted = False
        if not locked and t >= START_DAY and np.isfinite(v):
            far = protect and np.isfinite(z) and len(learned) >= 7 and abs(z) > ACCEPT_Z
            if not far:
                learned.append(v)
                learned = learned[-WINDOW:]
                accepted = True
        row["learned_today"] = accepted

        # update estimate
        if not locked and len(learned) >= 3:
            center, scale = _estimate(np.array(learned), within_sd)
        hist_center.append(center)
        hist_scale.append(scale)

        # stability -> ready?
        ready = False
        c_move = s_move = np.nan
        if len(hist_center) > STABLE_LOOKBACK and np.isfinite(hist_center[-STABLE_LOOKBACK - 1]):
            c_old, s_old = hist_center[-STABLE_LOOKBACK - 1], hist_scale[-STABLE_LOOKBACK - 1]
            c_move = abs(center - c_old) / scale
            s_move = abs(scale - s_old) / s_old
            ready = (len(learned) >= MIN_DAYS_READY and c_move < CENTER_TOL and s_move < SCALE_TOL)

        # lock: when ready, or forced
        if not locked and (ready or (force_lock_day is not None and t >= force_lock_day)):
            locked, lock_day, lock_ready = True, t, ready

        row.update(space_center=round(center, 3) if np.isfinite(center) else np.nan,
                   space_scale=round(scale, 3) if np.isfinite(scale) else np.nan,
                   good_days=len(learned),
                   center_move_14d=round(c_move, 3) if np.isfinite(c_move) else np.nan,
                   scale_move_14d=round(s_move, 3) if np.isfinite(s_move) else np.nan,
                   ready=bool(ready) if not locked or t == lock_day else bool(lock_ready),
                   locked=locked)
        rows.append(row)

    out = pd.DataFrame(rows)
    out.attrs.update(lock_day=lock_day, lock_ready=lock_ready)
    return out


def run_crew(mission_df: pd.DataFrame, signals=None, force_lock_day=None, protect=True,
             astronaut_col="astronaut", day_col="day"):
    """Wide mission table -> (daily table, summary per astronaut x signal)."""
    signals = signals or [c for c in mission_df.columns if c in PRIORS]
    daily, summary = [], []
    for a, g in mission_df.sort_values(day_col).groupby(astronaut_col):
        for s in signals:
            r = run_space_normal(g[s].to_numpy(dtype=float), s, force_lock_day, protect)
            r.insert(0, "signal", s)
            r.insert(0, "astronaut", a)
            r["day"] = g[day_col].to_numpy()
            daily.append(r)
            first_drift = r.loc[r["drift"], "day"].min()
            summary.append(dict(astronaut=a, signal=s, lock_day=r.attrs["lock_day"],
                                ready_at_lock=r.attrs["lock_ready"],
                                space_center=r["space_center"].iloc[-1],
                                space_scale=r["space_scale"].iloc[-1],
                                first_drift_day=first_drift if pd.notna(first_drift) else None))
    return pd.concat(daily, ignore_index=True), pd.DataFrame(summary)


# -----------------------------------------------------------------------------
# Demo crew (only used without CSVs)
# -----------------------------------------------------------------------------
SETTLE_SHIFT = {"resting_hr": -0.8, "sleep_hours": -1.0, "skin_temp": 0.8, "breathing_rate": 0.6,
                "reaction_ms": 0.3, "mood": -0.3, "hrv_rmssd": 0.0, "vision_score": 0.0}
ILLNESS = {"resting_hr": 1.0, "hrv_rmssd": -1.0, "sleep_hours": -0.7, "reaction_ms": 0.8,
           "mood": -0.8, "skin_temp": 0.9, "breathing_rate": 0.7, "vision_score": 0.0}


def demo_crew(seed=1, n=4, pre_days=20, days=200, illness_day=35, decline_start=110):
    """Pre-launch + mission data with: settling shift, a 5-day illness, a slow vision decline."""
    rng = np.random.default_rng(seed)
    pre, mis = [], []
    for a in range(n):
        own = {s: p[0] + rng.normal(0, p[1]) for s, p in PRIORS.items()}
        for d in range(-pre_days, days):
            r = {"astronaut": f"A{a+1}", "day": d}
            for s, p in PRIORS.items():
                sd = p[2]
                v = own[s] + rng.normal(0, sd)
                if d >= 0:
                    v += SETTLE_SHIFT[s] * sd * (1 - np.exp(-d / 4))
                    if a == 1 and illness_day <= d < illness_day + 5:  # A2 gets ill
                        v += ILLNESS[s] * 2.5 * sd
                    if s == "vision_score" and a in (0, 2) and d >= decline_start:  # A1, A3 vision decline
                        v -= min((d - decline_start) / 60, 1) * 3.0 * sd
                r[s] = round(v, 2)
            (pre if d < 0 else mis).append(r)
    return pd.DataFrame(pre), pd.DataFrame(mis)


if __name__ == "__main__":
    MISSION_CSV = None   # e.g. "/kaggle/input/snooze/mission.csv" (columns: astronaut, day, signals...)
    FORCE_LOCK_DAY = None  # e.g. day of a predicted blackout

    if MISSION_CSV:
        mis = pd.read_csv(MISSION_CSV)
        mis = mis[mis["day"] >= 0]
    else:
        _, mis = demo_crew()

    pd.set_option("display.width", 220)
    daily, summary = run_crew(mis, force_lock_day=FORCE_LOCK_DAY, protect=True)
    daily.to_csv("baseline2_space_normal_daily.csv", index=False)
    summary.to_csv("baseline2_space_normal_summary.csv", index=False)

    print("Lock (handover-ready) day per astronaut x signal:")
    print(summary.pivot(index="signal", columns="astronaut", values="lock_day").to_string())
    print("\nHandover-ready day per astronaut (latest signal to lock):")
    print(summary.groupby("astronaut")["lock_day"].max().to_string())

    if not MISSION_CSV:
        print("\nPlanted slow vision decline (A1, A3 from day 110): first drift alarm day")
        v = summary[summary.signal == "vision_score"][["astronaut", "first_drift_day"]]
        print(v.to_string(index=False))

        # the key test: A2 is ill on days 35-39, while the space normal is still learning.
        # With protection, the sick days are skipped; without, they leak into "normal".
        ill = daily[(daily.astronaut == "A2") & daily.day.between(33, 41) & (daily.signal == "resting_hr")]
        print("\nA2's planted illness (days 35-39, during learning), resting_hr:")
        print(ill[["day", "value", "z_vs_space_normal", "learned_today", "space_center"]].to_string(index=False))
        unprot_daily, _ = run_crew(mis, protect=False, signals=["resting_hr"])
        a2p = daily[(daily.astronaut == "A2") & (daily.signal == "resting_hr")]
        a2u = unprot_daily[unprot_daily.astronaut == "A2"]
        print("\nA2 resting_hr space normal on day 45: protected %.2f vs unprotected %.2f"
              % (a2p[a2p.day == 45].space_center.iloc[0], a2u[a2u.day == 45].space_center.iloc[0]))
