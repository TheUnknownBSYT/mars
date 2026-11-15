"""
Replay REAL NASA radiation data (OSDR RadLab exports) through Mission Pulse.

Two layers, same idea as for the body signals:
  Layer 1 - danger watch (hours): hourly MEDIAN dose rate vs the previous week.
            Hourly medians ignore short blips (e.g. ISS crossing the South
            Atlantic Anomaly for ~10 min) but catch things that last hours
            (radiation belt passage, a solar particle event).
  Layer 2 - trend watch (days): daily median dose rate through the same
            baseline engine as the crew signals (baselines.run_detector).

It also writes radiation_calibration.csv: typical level and day-to-day wobble
per environment, to set the simulator's radiation numbers from real data.

Run:  python radiation_replay.py
      python radiation_replay.py --donki donki_sep.json   (overlay real storm dates)

UNITS: the RadLab export column is 'absorbed_dose_rate' with no unit in the
file. Check the instrument's Knowledgebase page in RadLab before quoting
numbers. Instrument dose rate is NOT astronaut effective dose (mSv).
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from baselines import DetectorConfig, run_detector, LIGHT_NAMES, GREEN, YELLOW, RED, GREY, BLUE

DATA = {
    # environment label: (file, short description)
    "Mars cruise (Liulin-MO, ExoMars TGO, 2016)": ("../../data/radiation_radlab/liulin_mo_cruise.csv", "cruise"),
    "Moon trip (Artemis I HERA-HSU1, Orion, 2022)": ("../../data/radiation_radlab/artemis1_hera_hsu1.csv", "moon_trip"),
    "Low Earth orbit (Lidal, ISS Columbus, 2020-23)": ("../../data/radiation_radlab/iss_lidal.csv", "iss"),
}
OUT = "results"
LIGHT_COLORS = {GREEN: "#2e9d5b", YELLOW: "#e0a800", RED: "#d03b3b", GREY: "#9a9a9a", BLUE: "#3b7dd8"}


def load_radlab(path: str) -> pd.Series:
    """Load a RadLab CSV export -> clean time series of absorbed_dose_rate."""
    d = pd.read_csv(path, parse_dates=["timestamp"])
    d = d.dropna(subset=["absorbed_dose_rate"]).sort_values("timestamp")
    # some exports repeat a row ~30 s later with the identical value: drop those
    dt = d["timestamp"].diff().dt.total_seconds()
    same = d["absorbed_dose_rate"].diff() == 0
    d = d[~(same & (dt < 120))]
    d = d[d["absorbed_dose_rate"] >= 0]
    return d.set_index("timestamp")["absorbed_dose_rate"]


def daily_summary(s: pd.Series) -> pd.DataFrame:
    cad = s.index.to_series().diff().dt.total_seconds().median()
    g = s.resample("D")
    out = pd.DataFrame({
        "median": g.median(), "mean": g.mean(), "p95": g.quantile(0.95), "max": g.max(),
        "n": g.count(),
    })
    out["coverage"] = out["n"] / (86400 / cad)
    # integrate rate over the day (rate unit x hours) using the mean rate
    out["daily_dose_rate_x_24h"] = out["mean"] * 24
    return out


def danger_watch(s: pd.Series, k_mad: float = 6.0, min_ratio: float = 1.5,
                 lookback_h: int = 7 * 24) -> pd.DataFrame:
    """Hourly median vs the previous week's hourly medians (robust)."""
    h = s.resample("h").median().to_frame("hourly_median")
    roll = h["hourly_median"].shift(1).rolling(lookback_h, min_periods=12)
    base = roll.median()
    mad = roll.apply(lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))), raw=True) * 1.4826
    # before a week of history exists, fall back to the whole-series median
    base = base.fillna(h["hourly_median"].median())
    mad = mad.fillna((h["hourly_median"] - h["hourly_median"].median()).abs().median() * 1.4826)
    h["baseline"] = base
    h["threshold"] = np.maximum(base + k_mad * mad, base * min_ratio)
    h["danger"] = h["hourly_median"] > h["threshold"]
    return h


def trend_watch(daily: pd.DataFrame, window_days: int = 28,
                min_coverage: float = 0.5) -> tuple[pd.DataFrame, object]:
    """
    Daily median through the same baseline engine as the crew signals.
    Radiation 'normal' itself moves over months (solar cycle, orbit height),
    so here the reference is a ROLLING 4-week median, not a locked baseline:
    we want "this week is unusual", not "2023 differs from 2020".
    """
    x = daily["median"].where(daily["coverage"] >= min_coverage).to_numpy()
    cfg = DetectorConfig(estimator="medmad", detector="shewhart_rolling", rolling="rollmed",
                         rolling_window=window_days, rolling_scale="rolling",
                         exclude_flagged=True, rebaseline_after=10,
                         threshold=3.0, red_threshold=6.0,
                         persist_k=2, persist_n=3, adaptation_days=-1,
                         post_window=(0, 13), drift_method=None, min_baseline_days=7,
                         flatline_days=10**6)
    out = run_detector(x, np.array([]), cfg, prior=None)
    res = daily.copy()
    res["z"] = out.z_post
    res["light"] = [LIGHT_NAMES[v] for v in out.light]
    res["grey_reason"] = out.grey_reason
    return res, out


def load_donki(path: str) -> list[pd.Timestamp]:
    """DONKI SEP export (JSON from the DONKI web service) -> event times."""
    with open(path) as f:
        js = json.load(f)
    return sorted(pd.to_datetime(e["eventTime"]).tz_localize(None) for e in js if "eventTime" in e)


def plot_one(name, h, trend, sep_times, path):
    fig, ax = plt.subplots(2, 1, figsize=(12, 6.5), sharex=False)
    ax[0].plot(h.index, h["hourly_median"], lw=0.7, color="#555", label="hourly median")
    ax[0].plot(h.index, h["threshold"], lw=0.8, color="#d03b3b", ls="--", label="danger threshold")
    dz = h[h["danger"]]
    ax[0].scatter(dz.index, dz["hourly_median"], s=12, color="#d03b3b", zorder=3, label="danger hour")
    ax[0].set_yscale("log")
    ax[0].set_title(f"{name}: danger watch (hours)", loc="left", fontsize=11)
    ax[0].set_ylabel("dose rate (file units)")
    ax[0].legend(fontsize=8, loc="upper right")
    codes = {v: k for k, v in LIGHT_NAMES.items()}
    cols = [LIGHT_COLORS[codes[l]] for l in trend["light"]]
    ax[1].plot(trend.index, trend["median"], lw=0.8, color="#777")
    ax[1].scatter(trend.index, trend["median"], c=cols, s=14, zorder=3)
    ax[1].set_title("trend watch (days): daily median, colored by light", loc="left", fontsize=11)
    ax[1].set_ylabel("daily median")
    for a in ax:
        for t in sep_times:
            if h.index.min() <= t <= h.index.max():
                a.axvline(t, color="#3b7dd8", lw=0.8, alpha=0.6)
        a.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(donki: str | None = None):
    os.makedirs(OUT, exist_ok=True)
    sep = load_donki(donki) if donki else []
    calib, report = [], []
    for name, (path, short) in DATA.items():
        s = load_radlab(path)
        daily = daily_summary(s)
        good = daily[daily["coverage"] >= 0.5]
        h = danger_watch(s)
        trend, _ = trend_watch(daily)
        trend.to_csv(f"{OUT}/radiation_trend_{short}.csv")
        h[h["danger"]].to_csv(f"{OUT}/radiation_danger_hours_{short}.csv")
        plot_one(name, h, trend, sep, f"{OUT}/radiation_{short}.png")
        calib.append(dict(environment=name, days=len(good),
                          typical_daily_median=round(good["median"].median(), 3),
                          day_to_day_sd=round(good["median"].diff().std() / np.sqrt(2), 3),
                          spread_of_daily_medians=round(good["median"].std(), 3),
                          p95_of_daily_medians=round(good["median"].quantile(0.95), 3),
                          max_single_reading=round(s.max(), 2),
                          cadence_seconds=float(s.index.to_series().diff().dt.total_seconds().median())))
        lights = trend["light"].value_counts().to_dict()
        danger_days = sorted(set(h.index[h["danger"]].date))
        report.append(dict(environment=name, start=str(s.index.min().date()), end=str(s.index.max().date()),
                           readings=len(s), danger_hours=int(h["danger"].sum()),
                           danger_days=", ".join(str(d) for d in danger_days[:12]) + (" ..." if len(danger_days) > 12 else ""),
                           **{f"days_{k}": v for k, v in lights.items()}))
        if sep:
            near = [t for t in sep if s.index.min() <= t <= s.index.max()]
            hit = sum(any(abs((pd.Timestamp(d) - t).days) <= 2 for d in danger_days) for t in near)
            report[-1]["donki_sep_events_in_range"] = len(near)
            report[-1]["sep_events_with_danger_flag_within_2_days"] = hit
    pd.DataFrame(calib).to_csv(f"{OUT}/radiation_calibration.csv", index=False)
    rep = pd.DataFrame(report)
    rep.to_csv(f"{OUT}/radiation_replay_report.csv", index=False)
    pd.set_option("display.width", 200)
    print(pd.DataFrame(calib).to_string(index=False))
    print()
    print(rep.to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--donki", help="DONKI SEP JSON file to overlay real storm dates")
    main(ap.parse_args().donki)
