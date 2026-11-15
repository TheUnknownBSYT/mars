"""
Mission Pulse - get better PRIORS numbers from WESAD (run on Kaggle)
====================================================================
Baseline 1 needs, per signal: (population mean, between-person SD,
within-person daily SD, valid range).

What WESAD CAN give you (15 people, calm "baseline" condition + stress condition):
  - population mean      -> average of each person's calm value
  - between-person SD    -> how much people differ from each other when calm
  - stress effect        -> how far each signal jumps under stress (for the simulator)
  for: resting heart rate, HRV (RMSSD), breathing rate, skin temperature

What WESAD CANNOT give you:
  - within-person DAILY SD. Each person was recorded once for ~2 hours, so we
    never see how they vary from day to day. Keep the third number in PRIORS
    from typical ranges / literature, and say so.

Kaggle setup
  1. Notebook -> Add Data -> attach the WESAD dataset (and your own 'snooze' dataset).
  2. Run this cell. It searches everything under /kaggle/input for S2.pkl ... S17.pkl.
  3. Copy the printed PRIORS lines into baseline1_prelaunch.py.
"""
from __future__ import annotations

import glob
import os
import pickle

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, butter, filtfilt

FS = 700          # chest device + labels sampling rate (Hz)
CALM, STRESS = 1, 2
WIN = 60          # seconds per window


def list_inputs(root="/kaggle/input"):
    """Show what's attached, so you can see your 'snooze' and WESAD folders."""
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        print(d)
        for f in sorted(glob.glob(os.path.join(d, "*")))[:10]:
            print("   ", os.path.basename(f))


def r_peaks(ecg, fs=FS):
    ecg = ecg - np.median(ecg)
    if abs(ecg.min()) > abs(ecg.max()):
        ecg = -ecg
    peaks, _ = find_peaks(ecg, distance=int(0.33 * fs), height=np.percentile(ecg, 98) * 0.5)
    return peaks / fs


def hr_and_rmssd(beat_times):
    rr = np.diff(beat_times)
    ok = (rr > 0.33) & (rr < 2.0)
    rr = rr[ok]
    if len(rr) < 20:
        return np.nan, np.nan
    # drop ectopic / missed beats: successive change > 20%
    good = np.abs(np.diff(rr)) / rr[:-1] < 0.2
    diffs = np.diff(rr)[good]
    rmssd = np.sqrt(np.mean(diffs ** 2)) * 1000 if len(diffs) > 10 else np.nan
    return 60 / np.median(rr), rmssd


def breathing_rate(resp, fs=FS):
    b, a = butter(2, [0.1, 0.7], btype="band", fs=fs)   # 6-42 breaths/min
    r = filtfilt(b, a, resp)
    peaks, _ = find_peaks(r, distance=int(1.4 * fs), prominence=np.std(r) * 0.3)
    return len(peaks) / (len(resp) / fs / 60)


def per_condition(sig, labels, fn, cond):
    """Apply fn to each 60 s window fully inside one condition; return the median."""
    idx = np.where(labels == cond)[0]
    if len(idx) == 0:
        return np.nan
    vals = []
    for start in range(idx[0], idx[-1] - WIN * FS, WIN * FS):
        seg = slice(start, start + WIN * FS)
        if np.all(labels[seg] == cond):
            v = fn(sig[seg])
            if np.isfinite(v):
                vals.append(v)
    return float(np.median(vals)) if vals else np.nan


def subject_row(path):
    with open(path, "rb") as f:
        d = pickle.load(f, encoding="latin1")
    lab = np.asarray(d["label"]).astype(int)
    ch = d["signal"]["chest"]
    ecg = np.asarray(ch["ECG"]).ravel()
    resp = np.asarray(ch["Resp"]).ravel()
    temp = np.asarray(ch["Temp"]).ravel()
    row = {"subject": os.path.basename(path).replace(".pkl", "")}
    for cond, name in [(CALM, "calm"), (STRESS, "stress")]:
        row[f"resting_hr_{name}"] = per_condition(ecg, lab, lambda s: hr_and_rmssd(r_peaks(s))[0], cond)
        row[f"hrv_rmssd_{name}"] = per_condition(ecg, lab, lambda s: hr_and_rmssd(r_peaks(s))[1], cond)
        row[f"breathing_rate_{name}"] = per_condition(resp, lab, breathing_rate, cond)
        row[f"skin_temp_{name}"] = per_condition(temp, lab, np.mean, cond)
    return row


def main(root="/kaggle/input"):
    files = sorted(glob.glob(os.path.join(root, "**", "S*.pkl"), recursive=True))
    files = [f for f in files if os.path.basename(f)[1:-4].isdigit()]
    if not files:
        print("No WESAD S*.pkl found. Attached datasets:")
        list_inputs(root)
        return None
    rows = []
    for p in files:
        try:
            rows.append(subject_row(p))
            print("ok  ", p)
        except Exception as e:
            print("skip", p, e)
    df = pd.DataFrame(rows).round(2)
    df.to_csv("wesad_per_subject.csv", index=False)
    print(df.to_string(index=False))

    # current daily SDs from baseline1 (WESAD can't give these)
    daily_sd = {"resting_hr": 3.0, "hrv_rmssd": 7.0, "breathing_rate": 0.8, "skin_temp": 0.25}
    ranges = {"resting_hr": (30, 200), "hrv_rmssd": (5, 250), "breathing_rate": (4, 60), "skin_temp": (25, 42)}
    print("\n# ---- paste into PRIORS in baseline1_prelaunch.py ----")
    print("# (mean, between-person SD) from WESAD calm condition, n = %d people;" % len(df))
    print("# daily SD kept from typical ranges (WESAD has one session per person)")
    summary = []
    for s in daily_sd:
        calm = df[f"{s}_calm"].dropna()
        stress = df[f"{s}_stress"].dropna()
        both = df[[f"{s}_calm", f"{s}_stress"]].dropna()
        jump = (both[f"{s}_stress"] - both[f"{s}_calm"]).median()
        print(f'    "{s}": ({calm.mean():.2f}, {calm.std(ddof=1):.2f}, {daily_sd[s]}, {ranges[s]}),')
        summary.append(dict(signal=s, n=len(calm), mean=calm.mean(), between_sd=calm.std(ddof=1),
                            median_stress_jump=jump, jump_in_daily_SDs=jump / daily_sd[s]))
    print("\nStress effect (for simulator event sizes):")
    print(pd.DataFrame(summary).round(2).to_string(index=False))
    return df


if __name__ == "__main__":
    main()
