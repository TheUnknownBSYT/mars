"""
Readiness decision: compares today with the astronaut's OWN normal.

Output = traffic light (GO / CAUTION / NO-GO / RETEST), a confidence level,
and a breakdown into 3 reaction-time components:
    alertness   (Round 1)
    decision    (Round 2 minus Round 1)
    adaptation  (Round 3 switch cost)
Pure Python: no pygame.
"""
import statistics as st

import config as C

COMPONENTS = ("alertness", "decision", "adaptation")

ADVICE = {
    "alertness": "Avoid long monitoring or vigilance-heavy tasks (EVA support, long console shifts).",
    "decision": "Double-check before acting on alarms; avoid time-critical choices (robotic arm, piloting).",
    "adaptation": "Avoid leading emergency or fast-changing procedures (docking, contingency ops).",
}


def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _truthy(x):
    return str(x).strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------- baseline
def build_baseline(history):
    """Robust personal baseline from past sessions (list of dicts, oldest first).

    Uses only valid sessions AFTER familiarisation, most recent N.
    Centre = median, spread = 1.4826 * MAD (robust SD), with a floor.
    Returns None if there are not enough sessions.
    """
    usable = [h for h in history
              if not _truthy(h.get("invalid"))
              and (_num(h.get("session_index")) or 0) > C.FAMILIARISATION_SESSIONS
              and h.get("data_source") != "practice"]
    usable = usable[-C.BASELINE_MAX_SESSIONS:]
    if len(usable) < C.BASELINE_MIN_SESSIONS:
        return None
    base = {"n": len(usable),
            "n_simulated": sum(1 for h in usable if h.get("data_source") == "simulated")}
    for key, floor in C.SPREAD_FLOORS.items():
        vals = [v for v in (_num(h.get(key)) for h in usable) if v is not None]
        if len(vals) < C.BASELINE_MIN_SESSIONS:
            continue
        centre = st.median(vals)
        mad = st.median([abs(v - centre) for v in vals])
        base[key] = {"centre": centre, "spread": max(1.4826 * mad, floor)}
    return base


def _z(base, key, value):
    if base is None or key not in base or value is None:
        return None
    b = base[key]
    return (value - b["centre"]) / b["spread"]


# ---------------------------------------------------------------- evaluate
def evaluate(scores, checkin, history, session_index):
    """Return the full readiness result for one session.

    scores        dict from scoring.score_session
    checkin       dict with sleep_hours, fatigue, stress, mood_pre
    history       previous session rows for this astronaut (oldest first)
    session_index 1-based number of this session
    """
    base = build_baseline(history)

    # ---- 1. data quality
    quality = []
    if (scores.get("r1_false_starts") or 0) > C.MAX_FALSE_STARTS:
        quality.append(f"{scores['r1_false_starts']} false starts in Round 1 (pressing before the alarm)")
    if (scores.get("r1_valid") or 0) < C.MIN_VALID_R1:
        quality.append(f"only {scores.get('r1_valid', 0)} valid alarm responses in Round 1")
    if (scores.get("r3_timeouts") or 0) > C.MAX_R3_TIMEOUTS:
        quality.append(f"{scores['r3_timeouts']} timeouts in Round 3")
    invalid = bool(quality)

    # ---- 2. component checks
    comp = {c: {"status": "normal", "reasons": [], "delta": None, "unit": "ms"} for c in COMPONENTS}

    def flag(c, text, severe=True):
        comp[c]["reasons"].append(text)
        if severe or comp[c]["status"] == "normal":
            comp[c]["status"] = "slower" if severe else "watch"

    s = scores
    if base:
        mode = "personal"
        # alertness
        z = _z(base, "r1_median_ms", s.get("r1_median_ms"))
        if "r1_median_ms" in base and s.get("r1_median_ms") is not None:
            comp["alertness"]["delta"] = s["r1_median_ms"] - base["r1_median_ms"]["centre"]
        if z is not None and z > C.Z_SLOWER:
            flag("alertness", f"reaction {s['r1_median_ms']} ms vs your normal ~{base['r1_median_ms']['centre']:.0f} ms")
        if "r1_lapses" in base and s.get("r1_lapses") is not None and \
                s["r1_lapses"] > base["r1_lapses"]["centre"] + 2:
            flag("alertness", f"{s['r1_lapses']} lapses vs your usual ~{base['r1_lapses']['centre']:.0f}")
        # decision
        z = _z(base, "decision_time_ms", s.get("decision_time_ms"))
        if "decision_time_ms" in base and s.get("decision_time_ms") is not None:
            comp["decision"]["delta"] = s["decision_time_ms"] - base["decision_time_ms"]["centre"]
        if z is not None and z > C.Z_SLOWER:
            flag("decision", f"decision time {s['decision_time_ms']} ms vs your normal ~{base['decision_time_ms']['centre']:.0f} ms")
        if "r2_false_alarms" in base and s.get("r2_false_alarms") is not None and \
                s["r2_false_alarms"] > base["r2_false_alarms"]["centre"] + 2:
            flag("decision", f"{s['r2_false_alarms']} shots at friendly satellites vs your usual ~{base['r2_false_alarms']['centre']:.0f}")
        # adaptation
        z = _z(base, "switch_cost_ms", s.get("switch_cost_ms"))
        if "switch_cost_ms" in base and s.get("switch_cost_ms") is not None:
            comp["adaptation"]["delta"] = s["switch_cost_ms"] - base["switch_cost_ms"]["centre"]
        if z is not None and z > C.Z_SWITCH_COST:
            flag("adaptation", f"switch cost +{s['switch_cost_ms']} ms vs your normal ~{base['switch_cost_ms']['centre']:.0f} ms")
        z = _z(base, "r3_accuracy", s.get("r3_accuracy"))
        if z is not None and z < -C.Z_SLOWER:
            flag("adaptation", f"order accuracy {s['r3_accuracy']:.0%} vs your normal ~{base['r3_accuracy']['centre']:.0%}")
    else:
        mode = "generic"
        g = C.GENERIC
        if s.get("r1_median_ms") is not None and s["r1_median_ms"] > g["r1_median_ms"]:
            flag("alertness", f"reaction {s['r1_median_ms']} ms is above the generic {g['r1_median_ms']} ms")
        if (s.get("r1_lapses") or 0) >= g["r1_lapses"]:
            flag("alertness", f"{s['r1_lapses']} lapses (>= {C.R1_LAPSE_MS} ms)")
        if (s.get("r2_false_alarms") or 0) >= g["r2_false_alarms"] or \
                (s.get("r2_accuracy") is not None and s["r2_accuracy"] < g["r2_accuracy"]):
            flag("decision", f"debris accuracy {s['r2_accuracy']:.0%}, {s['r2_false_alarms']} friendly-fire shots")
        if s.get("r3_accuracy") is not None and s["r3_accuracy"] < g["r3_accuracy"]:
            flag("adaptation", f"order accuracy {s['r3_accuracy']:.0%} is below the generic {g['r3_accuracy']:.0%}")

    slower = [c for c in COMPONENTS if comp[c]["status"] == "slower"]

    # ---- 3. context (what the astronaut reported)
    sleep = _num(checkin.get("sleep_hours"))
    fatigue = _num(checkin.get("fatigue"))
    stress = _num(checkin.get("stress"))
    context = []
    if sleep is not None and sleep < C.SHORT_SLEEP_H:
        context.append(f"short sleep ({sleep:g} h)")
    if fatigue is not None and fatigue >= C.HIGH_FATIGUE:
        context.append(f"high fatigue ({fatigue:.0f}/7)")
    tired = bool(context)
    if stress is not None and stress >= 4:
        context.append(f"high stress ({stress:.0f}/5)")

    # ---- 4. traffic light
    if invalid:
        status = "RETEST"
        headline = "Session not reliable - please retest"
        message = "Data-quality checks failed, so this session is not used for a decision or for your baseline."
    elif slower and tired:
        status = "NO-GO"
        headline = "Avoid safety-critical tasks today"
        message = ("Your " + " and ".join(slower) + " slowed down AND you reported " + " and ".join(
            c for c in context if not c.startswith("high stress")) +
            ". Tell your crew lead / flight surgeon and retest after rest.")
    elif slower:
        status = "CAUTION"
        headline = "Below your normal - retest in 2-4 h"
        message = ("Your " + " and ".join(slower) + " slowed down without a sleep/fatigue explanation. "
                   "Consider workload, stress, illness or distraction.")
    elif tired:
        status = "CAUTION"
        headline = "Scores OK, but you're running on low sleep"
        message = "Performance is fine now, but fatigue often catches up later in the day. Retest before critical tasks."
    else:
        status = "GO"
        headline = "Within your normal range"
        message = ("Alertness, decision and adaptation all look like your usual performance."
                   if base else "No concerns against the generic reference. Your personal baseline is still forming.")

    advice = [ADVICE[c] for c in slower] if status in ("NO-GO", "CAUTION") and slower else []

    # ---- 5. confidence
    if invalid:
        confidence, why = "LOW", "data-quality problems"
    elif base and base["n"] >= C.HIGH_CONFIDENCE_SESSIONS:
        confidence, why = "HIGH", f"personal baseline from {base['n']} sessions"
    elif base:
        confidence, why = "MEDIUM", f"personal baseline still forming ({base['n']} sessions)"
    elif session_index <= C.FAMILIARISATION_SESSIONS:
        confidence, why = "LOW", f"familiarisation session {session_index}/{C.FAMILIARISATION_SESSIONS}"
    else:
        confidence, why = "LOW", "not enough valid sessions yet - generic reference used"
    if base and base.get("n_simulated"):
        why += f" ({base['n_simulated']} SIMULATED)"

    baseline_mode = (f"personal_n{base['n']}" + (f"_sim{base['n_simulated']}" if base["n_simulated"] else "")) if base else "generic"
    if session_index <= C.FAMILIARISATION_SESSIONS:
        baseline_mode += "_familiarisation"

    return {
        "status": status, "headline": headline, "message": message, "advice": advice,
        "confidence": confidence, "confidence_why": why,
        "components": comp, "context": context, "quality": quality,
        "invalid": invalid, "mode": mode, "baseline": base, "baseline_mode": baseline_mode,
    }
