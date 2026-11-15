"""
Get REAL effect sizes from WESAD to make the simulator's events realistic.

What WESAD can and can't give you:
  CAN   - how much heart rate, breathing and skin conductance move under acute
          stress vs a calm baseline, per person (15 people, lab sessions).
  CAN'T - day-to-day wobble over months (each person was recorded for ~2 hours).
          For daily wobble use typical ranges or a long-term dataset (e.g. LifeSnaps).

Output: results/wesad_effects.csv with, per subject, calm vs stress means and the
difference (stress - calm) in real units. The script then converts the median
difference into DAILY-wobble units (what simulator.py's patterns use), using the
daily SDs in simulator.SIGNALS. Don't use "SDs within one lab session": wobble
inside 20 minutes is far smaller than day-to-day wobble, so effects look huge.

Run on Kaggle (attach the WESAD dataset; files are .../S2/S2.pkl ... S17/S17.pkl):
    python wesad_effects.py --root /kaggle/input/<wesad-folder>

NOTE: written without access to WESAD here, from its documented layout
(data['signal']['chest'|'wrist'][...], data['label'] at 700 Hz:
1 = baseline, 2 = stress, 3 = amusement). Check the first subject's output by eye.
"""
from __future__ import annotations

import argparse
import glob
import os
import pickle

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

FS_CHEST = 700  # Hz, chest device and labels


def heart_rate_from_ecg(ecg: np.ndarray, fs: int = FS_CHEST, win_s: int = 30) -> np.ndarray:
    """Very simple R-peak detector -> heart rate per 30 s window (bpm)."""
    ecg = ecg - np.median(ecg)
    if np.abs(np.min(ecg)) > np.abs(np.max(ecg)):  # some leads are upside down
        ecg = -ecg
    peaks, _ = find_peaks(ecg, distance=int(0.33 * fs), height=np.percentile(ecg, 98) * 0.5)
    t = peaks / fs
    rr = np.diff(t)
    ok = (rr > 0.33) & (rr < 2.0)  # 30-180 bpm
    centers, hr = t[1:][ok], 60 / rr[ok]
    n_win = int(len(ecg) / fs // win_s)
    out = np.full(n_win, np.nan)
    for w in range(n_win):
        m = (centers >= w * win_s) & (centers < (w + 1) * win_s)
        if m.sum() >= 5:
            out[w] = np.median(hr[m])
    return out


def windows_by_label(x: np.ndarray, labels: np.ndarray, fs: int, win_s: int = 30):
    n_win = int(len(labels) / fs // win_s)
    lab = np.array([np.bincount(labels[w * fs * win_s:(w + 1) * fs * win_s].astype(int)).argmax()
                    for w in range(n_win)])
    vals = np.array([np.nanmean(x[w * fs * win_s:(w + 1) * fs * win_s]) for w in range(n_win)])
    return vals, lab


def subject_effects(pkl_path: str) -> dict:
    with open(pkl_path, "rb") as f:
        d = pickle.load(f, encoding="latin1")
    labels = np.asarray(d["label"]).astype(int)
    chest = d["signal"]["chest"]
    out = {"subject": os.path.basename(pkl_path).replace(".pkl", "")}

    hr = heart_rate_from_ecg(np.asarray(chest["ECG"]).ravel())
    _, lab = windows_by_label(np.zeros(len(labels)), labels, FS_CHEST)
    lab = lab[: len(hr)]
    feats = {"heart_rate": hr}
    for name, key in [("skin_conductance", "EDA"), ("skin_temp", "Temp")]:
        v, _ = windows_by_label(np.asarray(chest[key]).ravel(), labels, FS_CHEST)
        feats[name] = v[: len(lab)]
    for name, v in feats.items():
        calm, stress = v[lab == 1], v[lab == 2]
        calm, stress = calm[np.isfinite(calm)], stress[np.isfinite(stress)]
        if len(calm) < 5 or len(stress) < 5:
            continue
        out[f"{name}_calm"] = round(float(np.mean(calm)), 3)
        out[f"{name}_stress"] = round(float(np.mean(stress)), 3)
        out[f"{name}_stress_minus_calm"] = round(float(np.mean(stress) - np.mean(calm)), 3)
    return out


def main(root: str):
    files = sorted(glob.glob(os.path.join(root, "**", "S*.pkl"), recursive=True))
    if not files:
        raise SystemExit(f"No S*.pkl files under {root}")
    rows = []
    for p in files:
        try:
            rows.append(subject_effects(p))
            print("ok", p)
        except Exception as e:  # keep going if one subject is odd
            print("skip", p, e)
    df = pd.DataFrame(rows)
    os.makedirs("results", exist_ok=True)
    df.to_csv("results/wesad_effects.csv", index=False)
    print(df.to_string(index=False))
    from simulator import SIGNALS
    daily_sd = {"heart_rate": SIGNALS["resting_hr"][2], "skin_temp": SIGNALS["skin_temp"][2]}
    print("\nMedian stress - calm across subjects, and in daily-wobble units for simulator.py:")
    for name, sd in daily_sd.items():
        col = f"{name}_stress_minus_calm"
        if col in df:
            med = df[col].median()
            print(f"  {name}: {med:+.2f} real units = {med / sd:+.2f} daily SDs")
    print("  (skin conductance has no daily column in the simulator yet)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="folder containing S2/S2.pkl ... S17/S17.pkl")
    main(ap.parse_args().root)
