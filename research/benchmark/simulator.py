"""
Mission Pulse crew simulator: fake but realistic daily data WITH ground-truth labels.

Why: no public astronaut wearable data exists, so we simulate a crew and
inject known events. Because we know where every event is, we can score
how well each baseline variant finds them (that's how we pick the best one).

Every number below is an ILLUSTRATIVE ASSUMPTION based on typical healthy-adult
ranges, not NASA data. Label all simulated data as simulated. Swap in values
from WESAD / published studies when you have them (see SIGNALS).

value(day) = personal normal + adaptation shift + fatigue (shared, slow)
             + day-to-day noise + injected events
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

# name: (population mean, between-person SD, within-person daily SD, valid range)
SIGNALS = {
    "resting_hr":     (62.0, 7.0, 3.0, (30, 200)),     # bpm
    "hrv_rmssd":      (45.0, 15.0, 7.0, (5, 250)),     # ms
    "sleep_hours":    (6.8, 0.6, 0.6, (0, 14)),        # hours
    "reaction_ms":    (280.0, 25.0, 15.0, (120, 1500)),# ms, reaction game
    "vision_score":   (90.0, 4.0, 1.5, (0, 100)),      # 0-100, vision game
    "mood":           (7.0, 1.0, 0.8, (1, 10)),        # 1-10 check-in
    "skin_temp":      (33.5, 0.5, 0.25, (25, 42)),     # deg C
    "breathing_rate": (14.0, 1.5, 0.8, (4, 60)),       # breaths/min
}
SIGNAL_NAMES = list(SIGNALS)

# Expected change after launch, in within-person SDs (illustrative)
ADAPTATION_SHIFT = {"resting_hr": -0.8, "sleep_hours": -1.0, "skin_temp": 0.8,
                    "breathing_rate": 0.6, "hrv_rmssd": 0.0, "reaction_ms": 0.3,
                    "vision_score": 0.0, "mood": -0.3}

# How a shared "fatigue" state pushes each signal (sign = direction when tired)
FATIGUE_LOADING = {"resting_hr": 0.4, "hrv_rmssd": -0.4, "sleep_hours": -0.3,
                   "reaction_ms": 0.5, "vision_score": 0.0, "mood": -0.4,
                   "skin_temp": 0.0, "breathing_rate": 0.1}

# Illness pattern: direction and relative strength per signal
ILLNESS_PATTERN = {"resting_hr": 1.0, "hrv_rmssd": -1.0, "sleep_hours": -0.7,
                   "reaction_ms": 0.8, "mood": -0.8, "skin_temp": 0.9,
                   "breathing_rate": 0.7, "vision_score": 0.0}

# Solar storm night (whole crew, shelter): poor sleep, worse mood, slower reactions
STORM_PATTERN = {"sleep_hours": -1.8, "mood": -1.2, "reaction_ms": 1.2, "resting_hr": 0.6}

# Labels (ground truth)
NORMAL, ADAPT, ACUTE, DRIFT, STORM, BLIP, SENSOR = range(7)
LABEL_NAMES = ["normal", "adaptation", "acute", "drift", "storm", "blip", "sensor"]


@dataclass
class Crew:
    mission: np.ndarray            # (A, S, T) daily values, NaN = missing
    prelaunch: np.ndarray          # (A, S, P)
    labels: np.ndarray             # (A, S, T) ground truth codes
    events: list = field(default_factory=list)   # dicts describing each event
    personal_normal: np.ndarray | None = None    # (A, S)
    priors: dict = field(default_factory=dict)   # signal -> (mean, between SD, within SD)
    signals: list = field(default_factory=lambda: SIGNAL_NAMES)


def simulate_crew(seed: int = 0, n_astronauts: int = 4, mission_days: int = 270,
                  prelaunch_days: int = 20, n_illness: int = 2, n_storms: int = 2,
                  n_blips: int = 3, with_drift: bool = True, with_sensor_faults: bool = True,
                  illness_size: tuple = (1.8, 3.0), drift_size: tuple = (2.5, 3.5),
                  prelaunch_outliers: int = 0) -> Crew:
    rng = np.random.default_rng(seed)
    A, S, T, P = n_astronauts, len(SIGNALS), mission_days, prelaunch_days
    mission = np.zeros((A, S, T))
    pre = np.zeros((A, S, P))
    labels = np.full((A, S, T), NORMAL, dtype=np.int8)
    events = []

    pop = np.array([SIGNALS[s][0] for s in SIGNALS])
    between = np.array([SIGNALS[s][1] for s in SIGNALS])
    within = np.array([SIGNALS[s][2] for s in SIGNALS])
    normal = pop + rng.normal(0, 1, (A, S)) * between          # each astronaut's own normal
    noise_sd = within * rng.uniform(0.8, 1.25, (A, S))          # people differ in how much they wobble

    days = np.arange(T)
    for a in range(A):
        # shared fatigue: slow AR(1) process
        fat = np.zeros(T + P)
        for t in range(1, T + P):
            fat[t] = 0.75 * fat[t - 1] + rng.normal(0, 0.35)
        for si, s in enumerate(SIGNALS):
            sd = noise_sd[a, si]
            # day-to-day noise with a little memory
            e = np.zeros(T + P)
            for t in range(1, T + P):
                e[t] = 0.3 * e[t - 1] + rng.normal(0, sd * np.sqrt(1 - 0.09))
            base = normal[a, si] + e + FATIGUE_LOADING[s] * fat * sd
            pre[a, si] = base[:P]
            adapt = ADAPTATION_SHIFT[s] * sd * (1 - np.exp(-days / 4.0))  # settles over ~2 weeks
            mission[a, si] = base[P:] + adapt
        labels[a, :, :15] = ADAPT

    # --- optional junk days in the pre-launch data (tests robustness) ---------
    for a in range(A):
        for si in range(S):
            for _ in range(prelaunch_outliers):
                t = int(rng.integers(0, P))
                pre[a, si, t] += rng.choice([-1, 1]) * 4.0 * noise_sd[a, si]

    # --- illness episodes (one astronaut at a time) ---------------------------
    for a in range(A):
        taken = set()
        for _ in range(n_illness):
            for _try in range(50):
                start = int(rng.integers(35, T - 10))
                dur = int(rng.integers(3, 7))
                span = set(range(start - 5, start + dur + 5))
                if not span & taken:
                    break
            taken |= span
            mag = rng.uniform(*illness_size)
            shape = np.sin(np.linspace(0.3, np.pi - 0.3, dur))  # rise and fall
            for si, s in enumerate(SIGNALS):
                w = ILLNESS_PATTERN[s]
                if w == 0:
                    continue
                mission[a, si, start:start + dur] += w * mag * noise_sd[a, si] * shape
                labels[a, si, start:start + dur] = ACUTE
            events.append(dict(kind="acute", astronaut=a, start=start, end=start + dur - 1,
                               signals=[s for s in SIGNALS if ILLNESS_PATTERN[s] != 0],
                               size_sd=round(mag, 2)))

    # --- solar storm nights (whole crew) ---------------------------------------
    for _ in range(n_storms):
        start = int(rng.integers(35, T - 5))
        dur = int(rng.integers(1, 3))
        for a in range(A):
            for si, s in enumerate(SIGNALS):
                if s in STORM_PATTERN:
                    mission[a, si, start:start + dur] += STORM_PATTERN[s] * noise_sd[a, si] * 1.5
                    labels[a, si, start:start + dur] = np.where(
                        labels[a, si, start:start + dur] == NORMAL, STORM, labels[a, si, start:start + dur])
        events.append(dict(kind="storm", astronaut="all", start=start, end=start + dur - 1,
                           signals=list(STORM_PATTERN)))

    # --- slow drift: vision for half the crew, HRV for the other half ----------
    if with_drift:
        for a in range(A):
            s = "vision_score" if a % 2 == 0 else "hrv_rmssd"
            si = SIGNAL_NAMES.index(s)
            start = int(rng.integers(45, 140))
            length = int(rng.integers(60, 100))
            size = rng.uniform(*drift_size) * noise_sd[a, si]
            size = min(size, 0.5 * (normal[a, si] - SIGNALS[s][3][0]))  # stay physically possible
            ramp = np.clip((days - start) / length, 0, 1) * size
            mission[a, si] -= ramp  # both decline when things go wrong
            lab = labels[a, si]
            drift_days = days >= start + 10  # first 10 days are too small to call
            labels[a, si] = np.where(drift_days & (lab == NORMAL), DRIFT, lab)
            events.append(dict(kind="drift", astronaut=a, start=start + 10, end=T - 1,
                               signals=[s], size_sd=round(size / noise_sd[a, si], 2)))

    # --- single-day blips (should NOT alarm) -----------------------------------
    for a in range(A):
        for _ in range(n_blips):
            si = int(rng.integers(0, S))
            t = int(rng.integers(35, T))
            if labels[a, si, t] == NORMAL:
                mission[a, si, t] += rng.choice([-1, 1]) * 3.2 * noise_sd[a, si]
                labels[a, si, t] = BLIP

    # --- sensor faults: dropout + stuck --------------------------------------
    if with_sensor_faults:
        for a in range(A):
            si = int(rng.integers(0, S))
            t0 = int(rng.integers(40, T - 8)); d = int(rng.integers(2, 6))
            mission[a, si, t0:t0 + d] = np.nan
            labels[a, si, t0:t0 + d] = SENSOR
            events.append(dict(kind="sensor_dropout", astronaut=a, start=t0, end=t0 + d - 1,
                               signals=[SIGNAL_NAMES[si]]))
            si2 = int(rng.integers(0, S))
            t1 = int(rng.integers(40, T - 8)); d2 = 4
            mission[a, si2, t1:t1 + d2] = mission[a, si2, t1]
            labels[a, si2, t1 + 2:t1 + d2] = SENSOR  # only detectable once it's been flat 3 days
            events.append(dict(kind="sensor_stuck", astronaut=a, start=t1 + 2, end=t1 + d2 - 1,
                               signals=[SIGNAL_NAMES[si2]]))

    # keep values physically possible (a drifting HRV can't go below ~5 ms)
    for si, s in enumerate(SIGNALS):
        lo, hi = SIGNALS[s][3]
        span = hi - lo
        mission[:, si] = np.clip(mission[:, si], lo + 0.02 * span if s != "vision_score" else lo, hi)
        pre[:, si] = np.clip(pre[:, si], lo, hi)
    # round like real devices would
    mission = np.round(mission, 2)
    pre = np.round(pre, 2)
    # population prior per signal: (mean, between-person SD, within-person SD)
    priors = {s: (SIGNALS[s][0], SIGNALS[s][1], SIGNALS[s][2]) for s in SIGNALS}
    return Crew(mission, pre, labels, events, normal, priors)


def crew_to_dataframe(crew: Crew):
    """Long table: one row per astronaut x mission day, one column per signal (+ label columns)."""
    import pandas as pd
    A, S, T = crew.mission.shape
    rows = []
    for a in range(A):
        for t in range(T):
            r = {"astronaut": f"A{a+1}", "mission_day": t}
            for si, s in enumerate(crew.signals):
                r[s] = crew.mission[a, si, t]
                r[f"label_{s}"] = LABEL_NAMES[crew.labels[a, si, t]]
            rows.append(r)
    return pd.DataFrame(rows)
