"""
Mission Pulse - Baseline 1: the PRE-LAUNCH (flat) baseline
==========================================================
Each astronaut's Earth normal, per signal, built from data collected before
launch. It is computed once and never changes during the mission.

What this file does
  1. Cleans pre-launch data (missing, impossible, stuck-sensor values removed)
  2. Fits a baseline per astronaut x signal: a "center" (typical value) and a
     "scale" (usual day-to-day wobble)
  3. Reports how trustworthy each baseline is (days used, uncertainty)
  4. Scores any later day: z = (value - center) / scale
     -> "how many usual wobbles away from your Earth normal"

Three estimators (pick with method=...):
  "meanstd" : mean and standard deviation (simple; one bad day drags it)
  "medmad"  : median and scaled MAD (robust, but noisy with few days)
  "shrink"  : median/MAD blended with a population prior (DEFAULT; fewest
              false alarms in our benchmark, best with few pre-launch days)

Kaggle: paste into one cell (or upload as a script) and run. With no CSV it
runs a demo on simulated data. To use your own data, set PRELAUNCH_CSV and
MISSION_CSV at the bottom. Expected columns (long or wide):
  wide: astronaut, day, resting_hr, hrv_rmssd, sleep_hours, ...
The population priors below are ILLUSTRATIVE typical-adult assumptions, not
NASA values. Replace them if you have better numbers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SD = 1.4826  # makes MAD comparable to a standard deviation

# signal: (population mean, between-person SD, within-person daily SD, valid range)
# First two numbers for resting_hr, hrv_rmssd, breathing_rate and skin_temp come
# from WESAD's calm condition (15 people; skin_temp excludes S2/S3, likely poor
# sensor contact). WESAD has one session per person, so the daily SD (third
# number) stays a typical-range assumption. Other signals: illustrative assumptions.
PRIORS = {
    "resting_hr":     (72.1, 11.5, 3.0, (30, 200)),     # bpm   WESAD calm (seated; likely above true resting)
    "hrv_rmssd":      (47.4, 24.0, 7.0, (5, 250)),      # ms    WESAD calm
    "sleep_hours":    (6.8, 0.6, 0.6, (0, 14)),         # hours assumption
    "reaction_ms":    (280.0, 25.0, 15.0, (120, 1500)), # ms    assumption (reaction test)
    "vision_score":   (1.65, 0.15, 0.10, (0, 2.5)),     # Starsight faint-vision score, logCS (higher = better); assumption
    "mood":           (7.0, 1.0, 0.8, (1, 10)),         # 1-10  assumption (check-in)
    "skin_temp":      (34.0, 0.6, 0.25, (25, 42)),      # deg C WESAD calm, chest
    "breathing_rate": (16.2, 1.8, 0.8, (4, 60)),        # /min  WESAD calm
}


# ---------------------------------------------------------------------------
# 1. Cleaning
# ---------------------------------------------------------------------------
# Game scores come in steps (staircases, medians, 1-5 scales), so repeats are normal: no stuck-sensor check for them.
NO_FLATLINE = {"reaction_ms", "vision_score", "mood"}


def clean(values, valid_range=None, flatline_days: int = 3, signal=None):
    """
    Returns (clean_values, reasons). Bad days become NaN and never enter the
    baseline: missing, outside the physically possible range, or part of a
    run of identical values >= flatline_days (stuck sensor).
    """
    x = np.asarray(values, dtype=float).copy()
    reasons = np.array([""] * len(x), dtype=object)
    reasons[~np.isfinite(x)] = "missing"
    if valid_range is not None:
        lo, hi = valid_range
        bad = np.isfinite(x) & ((x < lo) | (x > hi))
        reasons[bad] = "impossible value"
        x[bad] = np.nan
    # stuck sensor: same value repeated flatline_days+ times in a row
    i = 0 if signal not in NO_FLATLINE else len(x)
    while i < len(x):
        j = i
        while j + 1 < len(x) and np.isfinite(x[i]) and x[j + 1] == x[i]:
            j += 1
        if j - i + 1 >= flatline_days:
            reasons[i:j + 1] = "flatline (stuck sensor?)"
            x[i:j + 1] = np.nan
        i = j + 1
    return x, reasons


# ---------------------------------------------------------------------------
# 2. Estimators
# ---------------------------------------------------------------------------
def _meanstd(x):
    return float(np.mean(x)), float(np.std(x, ddof=1)) if len(x) > 1 else np.nan


def _medmad(x):
    med = float(np.median(x))
    return med, float(np.median(np.abs(x - med)) * MAD_TO_SD)


def _shrink(x, prior, n0):
    """
    Bayesian-style blend with the population.
    CENTER: people differ from each other far more than they wobble day to day,
            so a handful of personal days quickly dominates (normal-normal update).
    SCALE:  a wobble estimate needs many more days, so it is blended with the
            typical within-person SD; n0 = how many days the prior is "worth".
    """
    pop_mean, between_sd, within_sd = prior[:3]
    n = len(x)
    if n == 0:
        return pop_mean, within_sd
    med, mad = _medmad(x) if n >= 2 else (float(x[0]), within_sd)
    if not np.isfinite(mad) or mad == 0:
        mad = within_sd
    w_center = n * between_sd ** 2 / (n * between_sd ** 2 + within_sd ** 2)
    w_scale = n / (n + n0)
    center = w_center * med + (1 - w_center) * pop_mean
    scale = np.sqrt(w_scale * mad ** 2 + (1 - w_scale) * within_sd ** 2)
    return float(center), float(scale)


# ---------------------------------------------------------------------------
# 3. Fit one baseline
# ---------------------------------------------------------------------------
def fit_prelaunch_baseline(values, signal: str | None = None, method: str = "shrink",
                           prior=None, n0: float = 10.0, min_days: int = 5) -> dict:
    """
    values : pre-launch daily values for ONE astronaut and ONE signal
    signal : name in PRIORS (sets the prior and valid range), optional
    Returns a dict: center, scale, n_used, n_dropped, se_center, ready, note
    """
    prior = prior if prior is not None else (PRIORS.get(signal) if signal else None)
    valid = prior[3] if prior is not None and len(prior) > 3 else None
    x, reasons = clean(values, valid, signal=signal)
    good = x[np.isfinite(x)]
    n = len(good)

    if method == "shrink":
        if prior is None:
            raise ValueError("method='shrink' needs a prior (give signal= or prior=)")
        center, scale = _shrink(good, prior, n0)
    elif n < 2:
        center, scale = (float(good[0]) if n else np.nan), np.nan
    elif method == "medmad":
        center, scale = _medmad(good)
    elif method == "meanstd":
        center, scale = _meanstd(good)
    else:
        raise ValueError(f"unknown method {method}")

    # never let the wobble be silly-small (a perfectly quiet week would make
    # every tiny change look huge later)
    if prior is not None and np.isfinite(scale):
        scale = max(scale, 0.5 * prior[2])

    se_center = 1.2533 * scale / np.sqrt(n) if n and np.isfinite(scale) else np.nan
    ready = n >= min_days
    note = "ok" if ready else f"only {n} good days (< {min_days}); leaning on population prior"
    return dict(center=round(center, 3) if np.isfinite(center) else np.nan,
                scale=round(scale, 3) if np.isfinite(scale) else np.nan,
                n_used=n, n_dropped=int((reasons != "").sum()),
                se_center=round(float(se_center), 3) if np.isfinite(se_center) else np.nan,
                ready=ready, method=method, note=note)


# ---------------------------------------------------------------------------
# 4. Fit for a whole crew, and score later days
# ---------------------------------------------------------------------------
def fit_all(prelaunch_df: pd.DataFrame, signals=None, method: str = "shrink",
            astronaut_col: str = "astronaut") -> pd.DataFrame:
    """Wide pre-launch table -> one row per astronaut x signal."""
    signals = signals or [c for c in prelaunch_df.columns if c in PRIORS]
    rows = []
    for a, g in prelaunch_df.groupby(astronaut_col):
        for s in signals:
            b = fit_prelaunch_baseline(g[s].to_numpy(), signal=s, method=method)
            rows.append({"astronaut": a, "signal": s, **b})
    return pd.DataFrame(rows)


def score(values, baseline: dict) -> np.ndarray:
    """z = (value - center) / scale. NaN stays NaN."""
    return (np.asarray(values, dtype=float) - baseline["center"]) / baseline["scale"]


def score_all(mission_df: pd.DataFrame, baselines: pd.DataFrame,
              astronaut_col: str = "astronaut") -> pd.DataFrame:
    """Adds z_pre_<signal> columns: distance from each astronaut's Earth normal."""
    out = mission_df.copy()
    for (a, s), b in baselines.set_index(["astronaut", "signal"]).iterrows():
        if s not in out.columns:
            continue
        m = out[astronaut_col] == a
        out.loc[m, f"z_pre_{s}"] = score(out.loc[m, s], b).round(2)
    return out


# ---------------------------------------------------------------------------
# 5. Demo data (used only if you don't give CSVs)
# ---------------------------------------------------------------------------
def demo_data(seed: int = 0, n_astronauts: int = 4, pre_days: int = 20, mission_days: int = 60):
    rng = np.random.default_rng(seed)
    pre, mis = [], []
    for a in range(n_astronauts):
        own = {s: p[0] + rng.normal(0, p[1]) for s, p in PRIORS.items()}
        for d in range(-pre_days, mission_days):
            r = {"astronaut": f"A{a+1}", "day": d}
            for s, p in PRIORS.items():
                r[s] = round(own[s] + rng.normal(0, p[2]), 2)
            (pre if d < 0 else mis).append(r)
    pre, mis = pd.DataFrame(pre), pd.DataFrame(mis)
    # sprinkle realistic junk into pre-launch: a sick day, a dead sensor, a stuck sensor
    pre.loc[3, "resting_hr"] += 15
    pre.loc[5, "sleep_hours"] = np.nan
    pre.loc[25:28, "hrv_rmssd"] = 41.0
    return pre, mis


def compare_methods(prelaunch_df: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side of the three estimators (handy for the pitch/Q&A)."""
    frames = [fit_all(prelaunch_df, method=m)[["astronaut", "signal", "center", "scale"]]
              .rename(columns={"center": f"center_{m}", "scale": f"scale_{m}"})
              for m in ("meanstd", "medmad", "shrink")]
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=["astronaut", "signal"])
    return out


if __name__ == "__main__":
    PRELAUNCH_CSV = None   # e.g. "/kaggle/input/mission-pulse/prelaunch.csv"
    MISSION_CSV = None     # e.g. "/kaggle/input/mission-pulse/mission.csv"

    if PRELAUNCH_CSV:
        pre = pd.read_csv(PRELAUNCH_CSV)
        mis = pd.read_csv(MISSION_CSV) if MISSION_CSV else None
    else:
        pre, mis = demo_data()

    pd.set_option("display.width", 200)
    baselines = fit_all(pre, method="shrink")
    print("Pre-launch baselines (shrink):")
    print(baselines.to_string(index=False))
    baselines.to_csv("baseline1_prelaunch.csv", index=False)

    print("\nThree estimators side by side (astronaut A1):")
    cm = compare_methods(pre)
    print(cm[cm.astronaut == cm.astronaut.iloc[0]].to_string(index=False))

    if mis is not None:
        scored = score_all(mis, baselines)
        scored.to_csv("mission_scored_vs_prelaunch.csv", index=False)
        zcols = [c for c in scored.columns if c.startswith("z_pre_")]
        print("\nFirst mission days, z vs Earth normal:")
        print(scored[["astronaut", "day"] + zcols].head(8).to_string(index=False))
        print("\nShare of days beyond |z| > 2.5 (should be small for healthy demo data):")
        print((scored[zcols].abs() > 2.5).mean().round(3).to_string())
