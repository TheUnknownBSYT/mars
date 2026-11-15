"""
Turns raw trial results into the numbers we care about.

Each trial result is a dict with at least:
  round, response, correct, rt_ms (float or None)
Pure Python: no pygame.
"""
import statistics as st

import config as C


# ---------------------------------------------------------------- helpers
def _median(v):
    return st.median(v) if v else None


def _mean(v):
    return st.fmean(v) if v else None


def _sd(v):
    return st.stdev(v) if len(v) >= 2 else None


def _rnd(x, nd=0):
    if x is None:
        return None
    return round(x, nd) if nd else int(round(x))


def _tail_mean(v, frac, slowest):
    """Mean of the fastest (or slowest) `frac` of values (at least one value)."""
    if not v:
        return None
    s = sorted(v, reverse=slowest)
    k = max(1, int(round(len(s) * frac)))
    return st.fmean(s[:k])


# ---------------------------------------------------------------- Round 1
def score_round1(trials):
    """Alertness (PVT-B style)."""
    hits = [t for t in trials if t["response"] == "hit"]
    rts = [t["rt_ms"] for t in hits]
    lapses = sum(1 for r in rts if r >= C.R1_LAPSE_MS)
    misses = sum(1 for t in trials if t["response"] == "miss")
    false_starts = sum(1 for t in trials if t["response"] == "false_start")

    # time-on-task: median RT of last third minus first third (positive = slowing down)
    tot = None
    if len(hits) >= 9:
        third = len(hits) // 3
        first = [t["rt_ms"] for t in hits[:third]]
        last = [t["rt_ms"] for t in hits[-third:]]
        tot = _median(last) - _median(first)

    return {
        "r1_valid": len(rts),
        "r1_median_ms": _rnd(_median(rts)),
        "r1_mean_ms": _rnd(_mean(rts)),
        "r1_sd_ms": _rnd(_sd(rts)),
        # NASA's primary PVT outcome: response speed = mean of 1/RT (per second)
        "r1_speed": _rnd(_mean([1000.0 / r for r in rts]), 3),
        "r1_fast10_ms": _rnd(_tail_mean(rts, 0.10, slowest=False)),
        "r1_slow10_ms": _rnd(_tail_mean(rts, 0.10, slowest=True)),
        "r1_lapses": lapses + misses,          # PVT counts no-responses as lapses too
        "r1_misses": misses,
        "r1_false_starts": false_starts,
        "r1_time_on_task_ms": _rnd(tot),
    }


# ---------------------------------------------------------------- Round 2
def score_round2(trials):
    """Decision speed + self-control (go / no-go)."""
    go = [t for t in trials if t["condition"] == "go"]
    nogo = [t for t in trials if t["condition"] == "no_go"]
    hits = [t for t in go if t["response"] == "hit"]
    misses = sum(1 for t in go if t["response"] == "miss")
    fas = sum(1 for t in nogo if t["response"] == "false_alarm")
    crs = sum(1 for t in nogo if t["response"] == "correct_rejection")
    early = sum(1 for t in trials if t["response"] == "false_start")
    n = len(trials) or 1
    return {
        "r2_go_rt_ms": _rnd(_median([t["rt_ms"] for t in hits])),
        "r2_hits": len(hits),
        "r2_misses": misses,
        "r2_false_alarms": fas,
        "r2_correct_holds": crs,
        "r2_false_starts": early,
        "r2_accuracy": _rnd((len(hits) + crs) / n, 3),
    }


# ---------------------------------------------------------------- Round 3
def score_round3(trials):
    """Adaptation (task switching)."""
    ok = [t for t in trials if t["correct"]]
    sw = [t["rt_ms"] for t in ok if t["condition"] == "switch"]
    rep = [t["rt_ms"] for t in ok if t["condition"] == "repeat"]
    n_switch = sum(1 for t in trials if t["condition"] == "switch")
    sw_ok = sum(1 for t in trials if t["condition"] == "switch" and t["correct"])
    old_rule = sum(1 for t in trials if t["response"] == "old_rule")
    timeouts = sum(1 for t in trials if t["response"] == "miss")
    sw_m, rep_m = _median(sw), _median(rep)
    n = len(trials) or 1
    return {
        "r3_switch_rt_ms": _rnd(sw_m),
        "r3_repeat_rt_ms": _rnd(rep_m),
        "switch_cost_ms": _rnd(sw_m - rep_m) if sw_m is not None and rep_m is not None else None,
        "r3_accuracy": _rnd(len(ok) / n, 3),
        "r3_switch_accuracy": _rnd(sw_ok / n_switch, 3) if n_switch else None,
        "r3_old_rule_errors": old_rule,
        "r3_errors": n - len(ok) - timeouts,
        "r3_timeouts": timeouts,
    }


# ---------------------------------------------------------------- all
def score_session(r1_trials, r2_trials, r3_trials):
    out = {}
    out.update(score_round1(r1_trials))
    out.update(score_round2(r2_trials))
    out.update(score_round3(r3_trials))
    # Decision time = extra time to CHOOSE, on top of basic alertness
    if out["r2_go_rt_ms"] is not None and out["r1_median_ms"] is not None:
        out["decision_time_ms"] = out["r2_go_rt_ms"] - out["r1_median_ms"]
    else:
        out["decision_time_ms"] = None
    # Same column name as the simulated crew data -> plugs into Baseline 1 & 2
    out["reaction_ms"] = out["r1_median_ms"]
    return out
