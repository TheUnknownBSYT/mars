"""
Benchmark every baseline variant on simulated crews with known events,
then pick the best one.

How "best" is decided (say this in the pitch):
  - alarm budget: at most ~1 false-alarm day per astronaut per month
  - within that budget, catch as many real events as possible
    (illness = acute, slow decline = drift), as early as possible
  - tuned on one set of simulated crews, then re-checked on DIFFERENT crews
    so we don't fool ourselves

Run:  python benchmark.py            (full run, a few minutes)
      python benchmark.py --quick    (small run to check everything works)
Outputs go to results/.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from dataclasses import asdict, replace
from multiprocessing import Pool

import numpy as np
import pandas as pd

from baselines import (DetectorConfig, run_detector, crew_environment_shift,
                       apply_corroboration, GREEN, YELLOW, RED, GREY, BLUE)
from simulator import (simulate_crew, SIGNALS, SIGNAL_NAMES, NORMAL, ADAPT, ACUTE,
                       DRIFT, STORM, BLIP, SENSOR)

OUT = "results"
ALARM = (YELLOW, RED)
_CREW_CACHE: dict = {}


def get_crew(seed: int, **kw):
    key = (seed, tuple(sorted(kw.items())))
    if key not in _CREW_CACHE:
        _CREW_CACHE[key] = simulate_crew(seed, **kw)
    return _CREW_CACHE[key]


def run_crew(cfg: DetectorConfig, crew, use_env: bool = False):
    """Run one config on one crew. Returns lights (A, S, T)."""
    A, S, T = crew.mission.shape
    lights = np.zeros((A, S, T), dtype=np.int8)
    zpost = np.zeros((A, S, T))
    envs = np.zeros((S, T), dtype=bool)
    for si, s in enumerate(crew.signals):
        c = replace(cfg, valid_range=SIGNALS[s][3])
        if cfg.drift_signals and s not in cfg.drift_signals:
            c = replace(c, drift_method=None)
        outs = [run_detector(crew.mission[a, si], crew.prelaunch[a, si], c, crew.priors[s])
                for a in range(A)]
        if use_env:
            env = crew_environment_shift(np.vstack([o.z_post for o in outs]))
            envs[si] = env
            outs = [run_detector(crew.mission[a, si], crew.prelaunch[a, si], c, crew.priors[s],
                                 environment_shift=env) for a in range(A)]
        for a, o in enumerate(outs):
            lights[a, si] = o.light
            zpost[a, si] = o.z_post
    if cfg.corroborate_m:
        for a in range(A):
            lights[a] = apply_corroboration(lights[a], zpost[a], cfg, envs if use_env else None)
    return lights


def score_crew(lights, crew):
    """Compare lights with the ground truth."""
    A, S, T = lights.shape
    lab = crew.labels
    alarm = np.isin(lights, ALARM)
    m = {}

    # acute (illness): caught if any affected signal alarms during the event (+2 days grace)
    hits, delays = [], []
    for ev in crew.events:
        if ev["kind"] != "acute":
            continue
        a = ev["astronaut"]
        idx = [crew.signals.index(s) for s in ev["signals"]]
        win = slice(ev["start"], min(ev["end"] + 3, T))
        any_alarm = alarm[a, idx, win].any(axis=0)
        hit = bool(any_alarm.any())
        hits.append(hit)
        if hit:
            delays.append(int(np.argmax(any_alarm)))
    m["acute_recall"] = float(np.mean(hits)) if hits else np.nan
    m["acute_delay"] = float(np.mean(delays)) if delays else np.nan

    # drift (slow decline): caught if the signal alarms within 60 days of becoming real
    hits, delays = [], []
    for ev in crew.events:
        if ev["kind"] != "drift":
            continue
        a, si = ev["astronaut"], crew.signals.index(ev["signals"][0])
        win = slice(ev["start"], min(ev["start"] + 60, T))
        al = alarm[a, si, win]
        hit = bool(al.any())
        hits.append(hit)
        if hit:
            delays.append(int(np.argmax(al)))
    m["drift_recall"] = float(np.mean(hits)) if hits else np.nan
    m["drift_delay"] = float(np.mean(delays)) if delays else np.nan

    # false alarms: an astronaut-day where some signal alarms but its own truth is normal/blip
    false_sig = alarm & np.isin(lab, (NORMAL, BLIP))
    false_days = false_sig.any(axis=1).sum()
    m["false_alarm_days_per_month"] = float(false_days / (A * T / 30.0))
    m["blip_alarm_rate"] = float(alarm[lab == BLIP].mean()) if (lab == BLIP).any() else np.nan
    m["adaptation_alarm_rate"] = float(alarm[lab == ADAPT].mean())
    m["sensor_grey_rate"] = float((lights[lab == SENSOR] == GREY).mean()) if (lab == SENSOR).any() else np.nan
    storm = lab == STORM
    m["storm_blue_rate"] = float((lights[storm] == BLUE).mean()) if storm.any() else np.nan
    m["storm_alarm_rate"] = float(alarm[storm].mean()) if storm.any() else np.nan
    return m


def evaluate(cfg: DetectorConfig, seeds, use_env=False, sim_kw=None):
    sim_kw = sim_kw or {}
    rows = [score_crew(run_crew(cfg, get_crew(s, **sim_kw), use_env), get_crew(s, **sim_kw))
            for s in seeds]
    df = pd.DataFrame(rows)
    out = df.mean(numeric_only=True).to_dict()
    out["config"] = cfg.name()
    return out


def _eval_star(args):
    cfg, seeds, use_env, sim_kw = args
    return evaluate(cfg, seeds, use_env, sim_kw)


def pick_best(df: pd.DataFrame, budget: float = 1.0):
    df = df.copy()
    df["detect_score"] = 0.6 * df["acute_recall"] + 0.4 * df["drift_recall"].fillna(0)
    ok = df[df["false_alarm_days_per_month"] <= budget]
    pool = ok if len(ok) else df
    return pool.sort_values(["detect_score", "acute_delay"], ascending=[False, True])


def stage1_grid():
    grid = []
    persist = [(1, 1), (2, 3), (3, 5)]
    for thr, (k, n) in itertools.product([2.0, 2.5, 3.0], persist):
        grid.append(DetectorConfig(detector="shewhart_post", threshold=thr, persist_k=k,
                                   persist_n=n, drift_method=None))
    rollings = [("sma", 7, 3.5), ("sma", 14, 3.5), ("rollmed", 7, 3.5), ("ewma", 7, 3.5), ("ewma", 7, 7.0)]
    for (r, w, hl), scale, excl, thr, (k, n) in itertools.product(
            rollings, ["fixed", "rolling"], [True, False], [2.0, 2.5, 3.0], persist[1:]):
        grid.append(DetectorConfig(detector="shewhart_rolling", rolling=r, rolling_window=w,
                                   ewma_halflife=hl, rolling_scale=scale, exclude_flagged=excl,
                                   threshold=thr, persist_k=k, persist_n=n, drift_method=None))
    for lam, L in itertools.product([0.2, 0.3, 0.5], [2.5, 2.7, 3.0]):
        grid.append(DetectorConfig(detector="ewma_chart", ewma_lambda=lam, ewma_L=L, drift_method=None))
    return grid


def main(quick=False):
    os.makedirs(OUT, exist_ok=True)
    tune = list(range(0, 3 if quick else 10))
    test = list(range(100, 103 if quick else 110))
    t0 = time.time()

    # ---------------- Stage 1: which acute detector? -----------------------
    grid = stage1_grid()
    if quick:
        grid = grid[::12]
    with Pool(2) as pool:
        res = pool.map(_eval_star, [(g, tune, False, None) for g in grid])
    s1 = pd.DataFrame(res)
    s1["_idx"] = range(len(grid))
    s1.to_csv(f"{OUT}/stage1_acute_detectors.csv", index=False)
    ranked = pick_best(s1)
    best1 = grid[int(ranked.iloc[0]["_idx"])]
    print(f"[stage 1] {len(grid)} variants in {time.time()-t0:.0f}s; best: {best1.name()}")

    # ---------------- Stage 1b: add multi-signal agreement? ---------------
    top = pick_best(s1, budget=2.0).head(6)["_idx"].astype(int).tolist()
    grid1b = []
    for i in top:
        grid1b.append(grid[i])
        for m, thr, (k, n) in itertools.product([3, 4], [2.0, 2.5], [(1, 1), (2, 3)]):
            grid1b.append(replace(grid[i], corroborate_m=m, corroborate_thr=thr,
                                  corroborate_k=k, corroborate_n=n))
    if quick:
        grid1b = grid1b[:6]
    with Pool(2) as pool:
        res = pool.map(_eval_star, [(g, tune, False, None) for g in grid1b])
    s1b = pd.DataFrame(res)
    s1b["_idx"] = range(len(grid1b))
    s1b.to_csv(f"{OUT}/stage1b_multi_signal_agreement.csv", index=False)
    best1 = grid1b[int(pick_best(s1b).iloc[0]["_idx"])]
    print(f"[stage 1b] best: {best1.name()}")

    # ---------------- Stage 2: add a slow-drift detector? ------------------
    slow = ("vision_score", "hrv_rmssd", "sleep_hours", "reaction_ms")
    grid2 = [replace(best1, drift_method=None)]
    for k, h, pw, ds in itertools.product([0.75, 1.0], [8.0, 12.0], [(15, 30), (15, 45)], [None, slow]):
        grid2.append(replace(best1, drift_method="cusum", cusum_k=k, cusum_h=h,
                             post_window=pw, drift_signals=ds))
    for w, z, p, pw, ds in itertools.product([14, 21], [2.5, 3.0], [3, 5], [(15, 30), (15, 45)],
                                             [None, slow]):
        grid2.append(replace(best1, drift_method="window_mean", drift_window=w, drift_z=z,
                             drift_persist=p, post_window=pw, drift_signals=ds))
    if quick:
        grid2 = grid2[::8]
    with Pool(2) as pool:
        res = pool.map(_eval_star, [(g, tune, False, None) for g in grid2])
    s2 = pd.DataFrame(res)
    s2["_idx"] = range(len(grid2))
    s2.to_csv(f"{OUT}/stage2_drift_detectors.csv", index=False)
    best2 = grid2[int(pick_best(s2).iloc[0]["_idx"])]
    print(f"[stage 2] best: {best2.name()}")

    # ---------------- Stage 3: which estimator for the fixed baselines? ----
    rows = []
    for est, pdays in itertools.product(["meanstd", "medmad", "shrink"], [5, 10, 20]):
        cfg = replace(best2, estimator=est)
        r = evaluate(cfg, tune, False, dict(prelaunch_days=pdays, prelaunch_outliers=1))
        r.update(estimator=est, prelaunch_days=pdays)
        rows.append(r)
    s3 = pd.DataFrame(rows)
    s3.to_csv(f"{OUT}/stage3_estimators.csv", index=False)
    s3_mean = s3.groupby("estimator")[["acute_recall", "drift_recall",
                                       "false_alarm_days_per_month"]].mean()
    s3_mean["detect_score"] = 0.6 * s3_mean["acute_recall"] + 0.4 * s3_mean["drift_recall"]
    # must respect the alarm budget; scores within 0.02 of each other are a tie
    # (noise), and ties go to the one with fewer false alarms
    ok = s3_mean[s3_mean["false_alarm_days_per_month"] <= 1.0]
    ok = ok if len(ok) else s3_mean
    top = ok["detect_score"].max()
    tied = ok[ok["detect_score"] >= top - 0.02]
    best_est = tied["false_alarm_days_per_month"].idxmin()
    print(f"[stage 3] best estimator: {best_est}")

    # ---------------- Two recommended operating points -------------------
    strict = replace(best2, estimator=best_est)

    # ---------------- Stage 4: a more sensitive mode (budget 2/month) -------
    # combine the best acute settings at budget 2 with the best drift settings at budget 2
    drift_best = grid2[int(pick_best(s2, budget=2.0).iloc[0]["_idx"])]
    drift_keys = dict(drift_method=drift_best.drift_method, drift_window=drift_best.drift_window,
                      drift_z=drift_best.drift_z, drift_persist=drift_best.drift_persist,
                      cusum_k=drift_best.cusum_k, cusum_h=drift_best.cusum_h,
                      post_window=drift_best.post_window, drift_signals=drift_best.drift_signals)
    cands = [replace(drift_best, estimator=best_est)]
    for i in pick_best(s1b, budget=2.0).head(3)["_idx"].astype(int):
        cands.append(replace(grid1b[i], estimator=best_est))
        cands.append(replace(grid1b[i], estimator=best_est, **drift_keys))
    with Pool(2) as pool:
        res = pool.map(_eval_star, [(g, tune, False, None) for g in cands])
    s4 = pd.DataFrame(res)
    s4["_idx"] = range(len(cands))
    s4.to_csv(f"{OUT}/stage4_balanced_mode.csv", index=False)
    balanced = cands[int(pick_best(s4, budget=2.0).iloc[0]["_idx"])]

    # ---------------- Final check on NEW crews, with ship-or-person on -----
    final_cfgs = {"STRICT (budget 1 false alarm/astronaut/month)": strict,
                  "BALANCED (budget 2/month)": balanced,
                  "naive reference (z>2.5 any day, mean/SD, nothing else)":
                      DetectorConfig(detector="shewhart_post", threshold=2.5, persist_k=1,
                                     persist_n=1, drift_method=None, estimator="meanstd")}
    final = []
    for label, cfg in final_cfgs.items():
        r = evaluate(cfg, test, use_env=True)
        r["which"] = label
        final.append(r)
    fdf = pd.DataFrame(final)
    fdf.to_csv(f"{OUT}/final_test_on_new_crews.csv", index=False)
    with open(f"{OUT}/best_config.json", "w") as f:
        json.dump(asdict(strict), f, indent=2)
    with open(f"{OUT}/balanced_config.json", "w") as f:
        json.dump(asdict(balanced), f, indent=2)
    print("STRICT  :", strict.name())
    print("BALANCED:", balanced.name())
    print(fdf.drop(columns=["config"]).round(3).to_string(index=False))
    print(f"done in {time.time()-t0:.0f}s")
    return strict, balanced, fdf


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
