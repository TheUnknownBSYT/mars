"""
Mission Pulse - Baseline 3: the FAST ROLLING baseline ("recent")
================================================================
How the astronaut has been over the last few days. It catches SUDDEN
changes (a bad night, a storm day, the start of an illness) that the slow
space normal is too steady to notice quickly.

How it behaves
  - Center = median of the last RECENT_DAYS good days (default 7), never
    including today (no peeking).
  - Wobble = NOT estimated from 7 days (far too noisy; our benchmark showed
    that). It borrows the space-normal wobble from baseline 2, or the typical
    daily wobble from PRIORS before baseline 2 has one.
  - A single far-off day (|z| > BLIP_Z) is marked "blip" and kept OUT of the
    recent window, so one weird day can't drag "recent" around. But if
    REBASE_AFTER far-off days come in a row, it accepts them: a real change
    should show up in "recent" quickly. That is the whole point of a fast baseline.
  - "sudden" = off by > SUDDEN_Z on SUDDEN_K of the last SUDDEN_N days.

It then puts all three baselines side by side (the four comparisons):
  today  vs recent        -> sudden blip?           (baseline 3)
  recent vs space normal  -> changed during mission? (3 vs 2)
  space  vs Earth normal  -> how much space changed you (2 vs 1, expected)
  recent vs Earth normal  -> total drift since Earth (3 vs 1)

Kaggle: run the baseline 1 and baseline 2 cells first, then this one.
No inputs needed: it runs on baseline 2's 200-day demo crew, plus a planted
one-day blip (A4, day 100) and a sudden 4-day sleep crash (A3, days 120-123).
"""
from __future__ import annotations

from collections import deque
import numpy as np
import pandas as pd

try:  # as files next to this one
    from baseline1_prelaunch import PRIORS, clean, fit_all
    from baseline2_space_normal import run_crew as run_space_crew, demo_crew
except ImportError:  # pasted into earlier notebook cells
    if "PRIORS" not in globals() or "demo_crew" not in globals():
        raise ImportError("Run the baseline 1 and baseline 2 cells first.")
    run_space_crew = run_crew  # noqa: F821  (baseline 2's function, from the earlier cell)

# ---- settings ----------------------------------------------------------------
RECENT_DAYS = 7      # length of the "recent" window
MIN_DAYS = 3         # need at least this many recent days to score
BLIP_Z = 3.0         # a day this far from recent is a blip, kept out of the window
REBASE_AFTER = 3     # ...unless this many far-off days in a row: then accept them
SUDDEN_Z = 3.0       # "sudden change" threshold
SUDDEN_K, SUDDEN_N = 2, 3   # ...on 2 of the last 3 days


def run_recent(values, signal: str, scale_by_day=None) -> pd.DataFrame:
    """
    values       : daily values for ONE astronaut and ONE signal (mission days 0..T-1)
    scale_by_day : optional wobble per day (e.g. baseline 2's space_scale); falls back
                   to the typical daily wobble in PRIORS where missing
    """
    prior = PRIORS[signal]
    x, reasons = clean(values, prior[3], signal=signal)
    T = len(x)
    window: deque = deque(maxlen=RECENT_DAYS)
    off_hist: deque = deque(maxlen=SUDDEN_N)
    far_run, pending = 0, []
    rows = []
    for t in range(T):
        v = x[t]
        scale = prior[2]
        if scale_by_day is not None and np.isfinite(scale_by_day[t]):
            scale = scale_by_day[t]
        center = float(np.median(window)) if len(window) >= MIN_DAYS else np.nan
        # a median of only a few days is itself uncertain: widen the wobble to match
        # (variance of a median ~ pi/2 * sd^2 / n)
        eff = scale * np.sqrt(1 + 1.571 / len(window)) if len(window) else scale
        z = (v - center) / eff if np.isfinite(v) and np.isfinite(center) else np.nan

        blip = bool(np.isfinite(z) and abs(z) > BLIP_Z)
        off_hist.append(bool(np.isfinite(z) and abs(z) > SUDDEN_Z))
        sudden = sum(off_hist) >= SUDDEN_K

        # update the recent window (today only affects tomorrow)
        if np.isfinite(v):
            if blip:
                far_run += 1
                pending.append(v)
                if far_run >= REBASE_AFTER:   # it's a real change, follow it
                    window.extend(pending)
                    far_run, pending = 0, []
            else:
                window.append(v)
                far_run, pending = 0, []

        rows.append(dict(day=t, value=values[t], grey_reason=reasons[t],
                         recent_center=round(center, 3) if np.isfinite(center) else np.nan,
                         recent_scale=round(scale, 3),
                         z_vs_recent=round(z, 2) if np.isfinite(z) else np.nan,
                         blip=blip, sudden=sudden))
    return pd.DataFrame(rows)


def run_recent_crew(mission_df, space_daily=None, signals=None,
                    astronaut_col="astronaut", day_col="day") -> pd.DataFrame:
    """Wide mission table (+ optional baseline 2 daily table) -> one row per astronaut x signal x day."""
    signals = signals or [c for c in mission_df.columns if c in PRIORS]
    out = []
    for a, g in mission_df.sort_values(day_col).groupby(astronaut_col):
        for s in signals:
            scale = None
            if space_daily is not None:
                sd = (space_daily[(space_daily.astronaut == a) & (space_daily.signal == s)]
                      .set_index("day")["space_scale"])
                scale = sd.reindex(g[day_col]).to_numpy(dtype=float)
            r = run_recent(g[s].to_numpy(dtype=float), s, scale)
            r.insert(0, "signal", s)
            r.insert(0, "astronaut", a)
            r["day"] = g[day_col].to_numpy()
            out.append(r)
    return pd.concat(out, ignore_index=True)


def four_comparisons(earth: pd.DataFrame, space_daily: pd.DataFrame,
                     recent_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Puts the three baselines side by side, per astronaut x signal x day.
    All differences are in "usual wobbles" so signals can be compared.
    """
    m = recent_daily.merge(
        space_daily[["astronaut", "signal", "day", "space_center", "space_scale",
                     "z_vs_space_normal", "locked", "drift"]],
        on=["astronaut", "signal", "day"], how="left")
    m = m.merge(earth[["astronaut", "signal", "center", "scale"]]
                .rename(columns={"center": "earth_center", "scale": "earth_scale"}),
                on=["astronaut", "signal"], how="left")
    w = m["space_scale"].fillna(m["earth_scale"])
    m["today_vs_recent"] = m["z_vs_recent"]
    m["recent_vs_space"] = ((m["recent_center"] - m["space_center"]) / w).round(2)
    m["space_vs_earth"] = ((m["space_center"] - m["earth_center"]) / m["earth_scale"]).round(2)
    m["recent_vs_earth"] = ((m["recent_center"] - m["earth_center"]) / m["earth_scale"]).round(2)
    return m


if __name__ == "__main__":
    MISSION_CSV = None     # e.g. "/kaggle/input/snooze/mission.csv"
    PRELAUNCH_CSV = None   # e.g. "/kaggle/input/snooze/prelaunch.csv"

    if MISSION_CSV:
        mis = pd.read_csv(MISSION_CSV)
        pre = pd.read_csv(PRELAUNCH_CSV) if PRELAUNCH_CSV else None
    else:
        pre, mis = demo_crew()
        # plant two extra events for baseline 3 to find
        sd_sleep = PRIORS["sleep_hours"][2]
        mis.loc[(mis.astronaut == "A4") & (mis.day == 100), "sleep_hours"] -= 3.5 * sd_sleep  # one bad night
        mis.loc[(mis.astronaut == "A3") & mis.day.between(120, 123), "sleep_hours"] -= 3.0 * sd_sleep  # 4-day crash

    pd.set_option("display.width", 220)
    space_daily, _ = run_space_crew(mis)                 # baseline 2
    recent = run_recent_crew(mis, space_daily)           # baseline 3
    recent.to_csv("baseline3_recent_daily.csv", index=False)

    if pre is not None:
        earth = fit_all(pre)                             # baseline 1
        comp = four_comparisons(earth, space_daily, recent)
        comp.to_csv("baselines_all_three_compared.csv", index=False)

    print("Days flagged per astronaut x signal:")
    print(recent.groupby(["signal", "astronaut"])[["blip", "sudden"]].sum()
          .unstack("astronaut").to_string())

    if not MISSION_CSV:
        def show(a, s, lo, hi, title):
            print(f"\n{title}")
            r = recent[(recent.astronaut == a) & (recent.signal == s) & recent.day.between(lo, hi)]
            print(r[["day", "value", "recent_center", "z_vs_recent", "blip", "sudden"]].to_string(index=False))
        show("A4", "sleep_hours", 98, 103, "A4 one bad night (day 100): should be a blip, NOT sudden")
        show("A3", "sleep_hours", 118, 127, "A3 4-day sleep crash (days 120-123): should turn sudden")
        show("A2", "resting_hr", 33, 41, "A2 illness (days 35-39): sudden?")
        if pre is not None:
            c = comp[(comp.astronaut == "A1") & (comp.signal == "vision_score")]
            print("\nA1 vision, all three baselines side by side (slow decline from day 110):")
            print(c[c.day.isin([60, 100, 130, 150, 170, 199])][
                ["day", "today_vs_recent", "recent_vs_space", "space_vs_earth", "recent_vs_earth", "drift"]
            ].to_string(index=False))
