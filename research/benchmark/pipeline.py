"""
Use this in the app: daily table in -> lights + explanations out.

    from pipeline import assess
    lights = assess(mission_df, prelaunch_df)

mission_df   : one row per astronaut per mission day:
               columns 'astronaut', 'mission_day', then one column per signal
prelaunch_df : same columns, rows from before launch ('mission_day' can be negative)

Returns one row per astronaut x day x signal with: value, light, the three
baseline comparisons (z vs pre-launch, vs space normal, vs recent days),
and a plain-English reason. Uses results/best_config.json if present
(written by benchmark.py), otherwise sensible defaults.
"""
from __future__ import annotations

import json
import os
from dataclasses import fields, replace

import numpy as np
import pandas as pd

from baselines import (DetectorConfig, run_detector, crew_environment_shift,
                       apply_corroboration, LIGHT_NAMES, GREEN, YELLOW, RED, GREY, BLUE)
from simulator import SIGNALS


def load_best_config(path: str = "results/best_config.json") -> DetectorConfig:
    if not os.path.exists(path):
        return DetectorConfig()
    with open(path) as f:
        raw = json.load(f)
    names = {f.name for f in fields(DetectorConfig)}
    raw = {k: (tuple(v) if isinstance(v, list) else v) for k, v in raw.items() if k in names}
    return DetectorConfig(**raw)


def _reason(light, z_pre, z_post, z_recent, grey_reason, drift):
    if light == GREY:
        return f"No reliable data ({grey_reason})."
    if light == BLUE:
        return "Changed, but explained: settling into space, or the whole crew shifted (check the ship)."
    if light in (YELLOW, RED):
        parts = []
        if np.isfinite(z_post):
            parts.append(f"{abs(z_post):.1f} usual wobbles {'above' if z_post > 0 else 'below'} your space normal")
        if drift:
            parts.append("a slow, steady change over the last weeks")
        if np.isfinite(z_recent) and abs(z_recent) > 2:
            parts.append("a sudden change vs your last few days")
        return "; ".join(parts).capitalize() + "."
    return "Within your normal."


def assess(mission_df: pd.DataFrame, prelaunch_df: pd.DataFrame,
           cfg: DetectorConfig | None = None, priors: dict | None = None) -> pd.DataFrame:
    cfg = cfg or load_best_config()
    priors = priors or {s: (v[0], v[1], v[2]) for s, v in SIGNALS.items()}
    signals = [c for c in mission_df.columns if c in priors]
    crew = sorted(mission_df["astronaut"].unique())
    days = np.sort(mission_df["mission_day"].unique())
    T = len(days)
    rows = []
    store = {}
    for s in signals:
        c = replace(cfg, valid_range=SIGNALS[s][3] if s in SIGNALS else None)
        if cfg.drift_signals and s not in cfg.drift_signals:
            c = replace(c, drift_method=None)
        series = {a: mission_df[mission_df.astronaut == a].set_index("mission_day")[s]
                  .reindex(days).to_numpy(dtype=float) for a in crew}
        pre = {a: prelaunch_df[prelaunch_df.astronaut == a][s].to_numpy(dtype=float) for a in crew}
        first = [run_detector(series[a], pre[a], c, priors[s]) for a in crew]
        env = crew_environment_shift(np.vstack([o.z_post for o in first])) if len(crew) >= 3 else None
        outs = [run_detector(series[a], pre[a], c, priors[s], environment_shift=env) for a in crew]
        store[s] = (outs, series, env)

    for ai, a in enumerate(crew):
        L = np.vstack([store[s][0][ai].light for s in signals])
        Z = np.vstack([store[s][0][ai].z_post for s in signals])
        E = np.vstack([store[s][2] if store[s][2] is not None else np.zeros(T, bool) for s in signals])
        L = apply_corroboration(L, Z, cfg, E)
        for si, s in enumerate(signals):
            o = store[s][0][ai]
            for t in range(T):
                rows.append(dict(
                    astronaut=a, mission_day=int(days[t]), signal=s,
                    value=store[s][1][a][t], light=LIGHT_NAMES[int(L[si, t])],
                    z_vs_prelaunch=round(o.z_pre[t], 2), z_vs_space_normal=round(o.z_post[t], 2),
                    z_vs_recent=round(o.z_recent[t], 2),
                    reason=_reason(int(L[si, t]), o.z_pre[t], o.z_post[t], o.z_recent[t],
                                   o.grey_reason[t], o.drift_flag[t])))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    # demo on a simulated crew
    from simulator import simulate_crew, crew_to_dataframe
    crew = simulate_crew(seed=7)
    mdf = crew_to_dataframe(crew)
    mdf = mdf[["astronaut", "mission_day"] + crew.signals]
    pre_rows = []
    for a in range(crew.prelaunch.shape[0]):
        for t in range(crew.prelaunch.shape[2]):
            r = {"astronaut": f"A{a+1}", "mission_day": t - crew.prelaunch.shape[2]}
            r.update({s: crew.prelaunch[a, si, t] for si, s in enumerate(crew.signals)})
            pre_rows.append(r)
    out = assess(mdf, pd.DataFrame(pre_rows))
    os.makedirs("results", exist_ok=True)
    out.to_csv("results/demo_lights.csv", index=False)
    print(out["light"].value_counts())
    print(out[out.light.isin(["yellow", "red"])].head(10).to_string(index=False))
