"""
Mission Pulse: personal baselines and status lights.

Three baselines per astronaut, per signal:
  1. PRE-LAUNCH  (flat)    - Earth normal, fixed forever.
  2. POST-LAUNCH (locked)  - space normal, learned on mission days 15-30, then frozen.
  3. RECENT      (rolling) - how the astronaut has been lately; keeps moving.

Every function here works on ONE astronaut and ONE signal: a daily series
(one number per day). Run it once per astronaut x signal.

Nothing here is a medical device. Lights show risk status, not a diagnosis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
import numpy as np

MAD_TO_SD = 1.4826  # makes MAD comparable to a standard deviation for normal data

# Light codes (ints are fast; names are for display)
GREEN, YELLOW, RED, GREY, BLUE = 0, 1, 2, 3, 4
LIGHT_NAMES = {GREEN: "green", YELLOW: "yellow", RED: "red", GREY: "grey", BLUE: "blue"}


# ---------------------------------------------------------------------------
# 1. Location / spread estimators (used by the fixed baselines)
# ---------------------------------------------------------------------------
def est_meanstd(x: np.ndarray) -> tuple[float, float]:
    """Plain mean and standard deviation. Simple, but one bad day drags both."""
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return np.nan, np.nan
    return float(np.mean(x)), float(np.std(x, ddof=1))


def est_medmad(x: np.ndarray) -> tuple[float, float]:
    """Median and scaled MAD. Barely moves when there is one weird day."""
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return np.nan, np.nan
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * MAD_TO_SD
    return med, mad


def est_shrink(x: np.ndarray, prior: tuple[float, float, float],
               n0: float = 10.0) -> tuple[float, float]:
    """
    Personal median/MAD blended with a population prior (Bayesian shrinkage).

    prior = (population mean, between-person SD, typical within-person daily SD)

    - CENTER: normal-normal update. Because people differ from each other a lot
      more than they wobble day to day, a handful of days is enough for the
      personal center to dominate.
    - SPREAD: a day-to-day spread estimate needs many more days, so it is
      blended with the typical within-person SD; n0 = how many days the prior
      spread is "worth".
    """
    pop_c, between_sd, within_sd = prior
    x = x[np.isfinite(x)]
    n = len(x)
    if n == 0:
        return float(pop_c), float(within_sd)
    med, mad = est_medmad(x) if n >= 2 else (float(x[0]), within_sd)
    if not np.isfinite(mad) or mad == 0:
        mad = within_sd
    w_c = n * between_sd ** 2 / (n * between_sd ** 2 + within_sd ** 2)
    center = w_c * med + (1 - w_c) * pop_c
    w_s = n / (n + n0)
    scale = np.sqrt(w_s * mad ** 2 + (1 - w_s) * within_sd ** 2)
    return float(center), float(scale)


ESTIMATORS = {"meanstd", "medmad", "shrink"}


def post_launch_baseline(vals: np.ndarray, method: str, pre_scale: float,
                         n0: float = 10.0) -> tuple[float, float]:
    """
    Space normal. The CENTER comes only from in-flight days (we expect it to
    differ from Earth, so we do NOT pull it back toward pre-launch). The SPREAD
    is blended with the pre-launch spread, because 15 days is too few to
    trust a spread estimate on its own.
    """
    vals = vals[np.isfinite(vals)]
    n = len(vals)
    if method == "meanstd":
        c, s = est_meanstd(vals)
    else:
        c, s = est_medmad(vals)
    if not np.isfinite(s) or s <= 0:
        s = pre_scale
    if method == "shrink":
        w = n / (n + n0)
        s = float(np.sqrt(w * s ** 2 + (1 - w) * pre_scale ** 2))
    return float(c), float(s)


def fixed_baseline(x: np.ndarray, method: str, prior: tuple[float, float, float] | None = None,
                   n0: float = 10.0) -> tuple[float, float]:
    if method == "meanstd":
        return est_meanstd(x)
    if method == "medmad":
        return est_medmad(x)
    if method == "shrink":
        if prior is None:
            raise ValueError("shrink needs a population prior (mean, between_sd, within_sd)")
        return est_shrink(x, prior, n0)
    raise ValueError(f"unknown estimator {method}")


# ---------------------------------------------------------------------------
# 2. Configuration of one detector variant
# ---------------------------------------------------------------------------
@dataclass
class DetectorConfig:
    # fixed baselines
    estimator: str = "shrink"            # meanstd | medmad | shrink
    shrink_n0: float = 10.0
    post_window: tuple[int, int] = (15, 30)   # mission days used for the post-launch baseline
    adaptation_days: int = 14            # days 0..N: expected change, shown blue

    # acute detector (the one that drives yellow/red)
    detector: str = "shewhart_post"      # shewhart_post | shewhart_rolling | ewma_chart
    threshold: float = 2.5               # |score| beyond this counts as "off"
    red_threshold: float = 4.0           # |score| beyond this (with persistence) -> red
    persist_k: int = 2                   # k of the last n days must be "off"
    persist_n: int = 3

    # rolling baseline (used by shewhart_rolling, and for "today vs recent" info)
    rolling: str = "ewma"                # sma | rollmed | ewma
    rolling_window: int = 7              # days, for sma / rollmed
    ewma_halflife: float = 3.5           # days, for ewma
    rolling_scale: str = "fixed"         # fixed (use pre/post spread) | rolling (own spread)
    exclude_flagged: bool = True         # don't let flagged/grey days update the rolling baseline
    rebaseline_after: int | None = None  # after this many alarm days in a row, accept the new
                                         # level (otherwise a permanent step = alarm forever)

    # EWMA control chart (detector == "ewma_chart")
    ewma_lambda: float = 0.3
    ewma_L: float = 2.7

    # slow-drift detector ("recent vs post-launch"). None = off
    #   cusum       : running total of small daily deviations (cusum_k, cusum_h)
    #   window_mean : median of the last drift_window days vs the post-launch
    #                 baseline, with the uncertainty of BOTH estimates included
    drift_method: str | None = "window_mean"
    cusum_h: float = 8.0
    cusum_k: float = 0.75
    drift_window: int = 14
    drift_z: float = 3.0
    drift_persist: int = 5
    drift_signals: tuple | None = None   # only watch these for drift (None = all)

    # multi-signal agreement (astronaut level): if at least corroborate_m signals
    # are past corroborate_thr on the same day, those signals go yellow even if
    # each one alone is too weak to call. None = off
    corroborate_m: int | None = None
    corroborate_thr: float = 2.0
    corroborate_k: int = 1
    corroborate_n: int = 1

    # data-quality rules (grey)
    min_baseline_days: int = 3
    flatline_days: int = 3               # identical value this many days in a row = stuck sensor
    valid_range: tuple[float, float] | None = None  # physically possible values

    def name(self) -> str:
        if self.detector == "shewhart_post":
            d = f"shewhart_post thr{self.threshold} {self.persist_k}of{self.persist_n}"
        elif self.detector == "shewhart_rolling":
            r = (f"{self.rolling}{self.rolling_window}" if self.rolling != "ewma"
                 else f"ewma_hl{self.ewma_halflife}")
            d = (f"shewhart_rolling[{r} scale={self.rolling_scale} "
                 f"excl={self.exclude_flagged}] thr{self.threshold} {self.persist_k}of{self.persist_n}")
        else:
            d = f"ewma_chart lam{self.ewma_lambda} L{self.ewma_L}"
        if self.drift_method == "cusum":
            c = f" + cusum k{self.cusum_k} h{self.cusum_h} post{self.post_window}"
        elif self.drift_method == "window_mean":
            c = (f" + window{self.drift_window} z{self.drift_z} x{self.drift_persist}d "
                 f"post{self.post_window}")
        else:
            c = ""
        if self.drift_method and self.drift_signals:
            c += f" on {'/'.join(self.drift_signals)}"
        if self.corroborate_m:
            c += (f" + agree>={self.corroborate_m}sig@{self.corroborate_thr} "
                  f"{self.corroborate_k}of{self.corroborate_n}")
        return f"{self.estimator} | {d}{c}"


# ---------------------------------------------------------------------------
# 3. The day-by-day engine
# ---------------------------------------------------------------------------
@dataclass
class DetectorOutput:
    light: np.ndarray            # per mission day, one of the light codes
    z_post: np.ndarray           # today vs fixed baseline (pre-launch until locked, then post-launch)
    z_recent: np.ndarray         # today vs rolling baseline (info: "sudden blip")
    z_pre: np.ndarray            # today vs pre-launch (info: total drift since Earth)
    acute_flag: np.ndarray       # bool: acute detector fired
    drift_flag: np.ndarray       # bool: CUSUM fired
    grey_reason: list = field(default_factory=list)
    pre: tuple = (np.nan, np.nan)
    post: tuple = (np.nan, np.nan)


def run_detector(mission: np.ndarray, prelaunch: np.ndarray, cfg: DetectorConfig,
                 prior: tuple[float, float, float] | None = None,
                 environment_shift: np.ndarray | None = None) -> DetectorOutput:
    """
    mission     : daily values for mission days 0..T-1 (NaN = missing)
    prelaunch   : daily values collected before launch (any length, NaN allowed)
    prior       : population (mean, between-person SD, within-person daily SD)
                  for this signal; needed for 'shrink', also sets a spread floor
    environment_shift : optional bool per day, True = the whole crew shifted together
                        (ship-or-person check says "ship"); those days show blue, not alarm.

    Causal: the baseline used on day t only uses data from before day t.
    """
    T = len(mission)
    light = np.full(T, GREEN, dtype=np.int8)
    z_post = np.full(T, np.nan)
    z_recent = np.full(T, np.nan)
    z_pre = np.full(T, np.nan)
    acute = np.zeros(T, dtype=bool)
    drift = np.zeros(T, dtype=bool)
    grey_reason = [""] * T

    # --- 1. pre-launch (flat) baseline -------------------------------------
    pre_c, pre_s = fixed_baseline(prelaunch, cfg.estimator, prior, cfg.shrink_n0)
    if prior is not None and (not np.isfinite(pre_s) or pre_s <= 0):
        pre_c, pre_s = prior[0], prior[2]
    # never let the spread get silly-small (a perfectly quiet week would make
    # every tiny wobble look huge)
    scale_floor = 0.5 * prior[2] if prior is not None else 1e-6

    post_c, post_s = np.nan, np.nan
    post_vals: list[float] = []
    post_locked = False

    # rolling state
    hist: deque = deque(maxlen=max(cfg.rolling_window, 1))
    ew_mean = np.nan
    ew_var = np.nan
    alpha = 1 - 0.5 ** (1 / cfg.ewma_halflife)

    # EWMA control chart state
    chart = np.nan

    # drift state
    c_pos = c_neg = 0.0
    recent_valid: deque = deque(maxlen=cfg.drift_window)
    drift_run = 0

    off_hist: deque = deque(maxlen=cfg.persist_n)
    alarm_run = 0
    last_vals: deque = deque(maxlen=cfg.flatline_days)

    for t in range(T):
        x = mission[t]

        # ---- reference = post-launch once locked, else pre-launch ---------
        if not post_locked and t > cfg.post_window[1]:
            if len(post_vals) >= cfg.min_baseline_days:
                post_c, post_s = post_launch_baseline(np.array(post_vals), cfg.estimator,
                                                      pre_s, cfg.shrink_n0)
            else:
                post_c, post_s = pre_c, pre_s
            post_locked = True
        if post_locked:
            ref_c, ref_s = post_c, post_s
        elif t > cfg.post_window[0] and len(post_vals) >= cfg.min_baseline_days:
            # provisional post-launch baseline while the window is still filling
            ref_c, ref_s = post_launch_baseline(np.array(post_vals), cfg.estimator,
                                                pre_s, cfg.shrink_n0)
        else:
            ref_c, ref_s = pre_c, pre_s
        ref_s = max(ref_s, scale_floor)

        # ---- data quality: grey -------------------------------------------
        reason = ""
        if not np.isfinite(x):
            reason = "missing"
        elif cfg.valid_range and not (cfg.valid_range[0] <= x <= cfg.valid_range[1]):
            reason = "impossible value"
        else:
            last_vals.append(x)
            if len(last_vals) == cfg.flatline_days and np.ptp(np.array(last_vals)) == 0:
                reason = "flatline (stuck sensor?)"
        if reason:
            light[t] = GREY
            grey_reason[t] = reason
            off_hist.append(False)
            continue  # bad data never touches any baseline

        # ---- scores ---------------------------------------------------------
        z_pre[t] = (x - pre_c) / max(pre_s, scale_floor)
        z_post[t] = (x - ref_c) / ref_s

        # rolling baseline (built only from accepted past days)
        if cfg.rolling == "ewma":
            roll_c = ew_mean
            roll_s = np.sqrt(ew_var) if np.isfinite(ew_var) else np.nan
            n_hist = 0 if not np.isfinite(ew_mean) else cfg.min_baseline_days
        else:
            arr = np.array(hist, dtype=float)
            n_hist = len(arr)
            if n_hist:
                roll_c = np.median(arr) if cfg.rolling == "rollmed" else np.mean(arr)
                roll_s = (np.median(np.abs(arr - np.median(arr))) * MAD_TO_SD
                          if cfg.rolling == "rollmed" else (np.std(arr, ddof=1) if n_hist > 1 else np.nan))
            else:
                roll_c = roll_s = np.nan
        if cfg.rolling_scale == "fixed" or not np.isfinite(roll_s):
            roll_s = ref_s
        roll_s = max(roll_s, scale_floor)
        if np.isfinite(roll_c) and n_hist >= cfg.min_baseline_days:
            z_recent[t] = (x - roll_c) / roll_s

        # ---- acute detector -------------------------------------------------
        if cfg.detector == "shewhart_post":
            score = z_post[t]
        elif cfg.detector == "shewhart_rolling":
            score = z_recent[t] if np.isfinite(z_recent[t]) else z_post[t]
        elif cfg.detector == "ewma_chart":
            chart = x if not np.isfinite(chart) else cfg.ewma_lambda * x + (1 - cfg.ewma_lambda) * chart
            sd_chart = ref_s * np.sqrt(cfg.ewma_lambda / (2 - cfg.ewma_lambda))
            score = (chart - ref_c) / sd_chart * (cfg.threshold / cfg.ewma_L)  # rescale so 'threshold' applies
        else:
            raise ValueError(cfg.detector)

        is_off = abs(score) > cfg.threshold
        off_hist.append(is_off)
        if cfg.detector == "ewma_chart":
            fired = is_off  # the chart already smooths; no extra persistence
        else:
            fired = sum(off_hist) >= cfg.persist_k
        acute[t] = fired

        # ---- drift detector ("recent vs post-launch", after lock) -----------
        recent_valid.append(x)
        if cfg.drift_method == "cusum" and post_locked:
            zc = np.clip(z_post[t], -4, 4)  # cap so one wild day can't trip it alone
            c_pos = max(0.0, c_pos + zc - cfg.cusum_k)
            c_neg = max(0.0, c_neg - zc - cfg.cusum_k)
            drift[t] = c_pos > cfg.cusum_h or c_neg > cfg.cusum_h
        elif cfg.drift_method == "window_mean" and post_locked and len(recent_valid) >= cfg.drift_window // 2:
            arr = np.array(recent_valid)
            n_post = max(len(post_vals), 1)
            # SE of a median ~ 1.25 * SD / sqrt(n); x1.3 for day-to-day memory
            se = 1.25 * ref_s * np.sqrt(1 / len(arr) + 1 / n_post) * 1.3
            zd = (np.median(arr) - ref_c) / se
            drift_run = drift_run + 1 if abs(zd) > cfg.drift_z else 0
            drift[t] = drift_run >= cfg.drift_persist

        # ---- light ----------------------------------------------------------
        # adaptation: first days in space, plus any days before the space
        # normal has enough data to stand on -> expected change, show blue
        in_adapt = t <= cfg.adaptation_days or (
            not post_locked and len(post_vals) < cfg.min_baseline_days)
        env = environment_shift is not None and bool(environment_shift[t])
        if fired or drift[t]:
            if in_adapt or env:
                light[t] = BLUE       # changed, but we know why
            elif fired and abs(score) > cfg.red_threshold:
                light[t] = RED
            else:
                light[t] = YELLOW
        else:
            light[t] = GREEN

        # ---- update baselines with today's value (only if accepted) --------
        alarm_run = alarm_run + 1 if light[t] in (YELLOW, RED) else 0
        accepted = ((not cfg.exclude_flagged) or light[t] in (GREEN, BLUE)
                    or (cfg.rebaseline_after is not None and alarm_run >= cfg.rebaseline_after))
        if accepted:
            if cfg.rolling == "ewma":
                if not np.isfinite(ew_mean):
                    ew_mean, ew_var = x, ref_s ** 2
                else:
                    d = x - ew_mean
                    ew_mean += alpha * d
                    ew_var = (1 - alpha) * (ew_var + alpha * d * d)
            else:
                hist.append(x)
            if not post_locked and cfg.post_window[0] <= t <= cfg.post_window[1]:
                post_vals.append(x)

    return DetectorOutput(light, z_post, z_recent, z_pre, acute, drift, grey_reason,
                          (pre_c, pre_s), (post_c, post_s))


# ---------------------------------------------------------------------------
# 4. Ship-or-person check (crew-wide shift -> environment, show blue)
# ---------------------------------------------------------------------------
def crew_environment_shift(z_by_astronaut: np.ndarray, thr: float = 2.0,
                           min_frac: float = 0.75) -> np.ndarray:
    """
    z_by_astronaut: array (n_astronauts, T) of z-scores for ONE signal.
    Returns bool per day: True if at least min_frac of the crew moved past thr
    in the same direction that day (=> probably the ship, not the person).
    """
    z = np.nan_to_num(z_by_astronaut, nan=0.0)
    n = z.shape[0]
    up = (z > thr).sum(axis=0)
    down = (z < -thr).sum(axis=0)
    return np.maximum(up, down) >= np.ceil(min_frac * n)


# ---------------------------------------------------------------------------
# 5. Combine signals into one light per astronaut per day
# ---------------------------------------------------------------------------
def combine_lights(lights_by_signal: np.ndarray) -> np.ndarray:
    """Worst light wins: red > yellow > grey > blue > green."""
    rank = {GREEN: 0, BLUE: 1, GREY: 2, YELLOW: 3, RED: 4}
    inv = {v: k for k, v in rank.items()}
    r = np.vectorize(rank.get)(lights_by_signal)
    return np.vectorize(inv.get)(r.max(axis=0))


# ---------------------------------------------------------------------------
# 6. Multi-signal agreement (one astronaut, all signals)
# ---------------------------------------------------------------------------
def apply_corroboration(lights: np.ndarray, z_post: np.ndarray, cfg: DetectorConfig,
                        environment_shift: np.ndarray | None = None) -> np.ndarray:
    """
    lights, z_post: arrays (n_signals, T) for ONE astronaut.
    environment_shift: optional bool array (n_signals, T): crew-wide shift per signal.
    Illness moves many signals at once; random noise rarely does. If enough
    signals are past a moderate threshold on the same day (with persistence),
    upgrade those signals from green to yellow.
    Skipped while the space normal is still being learned (adaptation).
    """
    if not cfg.corroborate_m:
        return lights
    out = lights.copy()
    S, T = z_post.shape
    z = np.nan_to_num(z_post, nan=0.0)
    beyond = np.abs(z) > cfg.corroborate_thr
    count = beyond.sum(axis=0)
    day_hit = count >= cfg.corroborate_m
    fired = np.zeros(T, dtype=bool)
    for t in range(T):
        lo = max(0, t - cfg.corroborate_n + 1)
        fired[t] = day_hit[lo:t + 1].sum() >= cfg.corroborate_k
    fired[: cfg.post_window[1] + 1] = False  # no space normal yet
    for t in np.where(fired)[0]:
        for si in range(S):
            if beyond[si, t] and out[si, t] == GREEN:
                if environment_shift is not None and environment_shift[si, t]:
                    out[si, t] = BLUE
                else:
                    out[si, t] = YELLOW
    return out
