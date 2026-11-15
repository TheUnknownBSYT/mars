"""
Readiness decision for DOCKMASTER: today vs the astronaut's OWN normal, split into
three components (hand_eye, memory, attention). Pure Python.

Anti-practice-effect design:
  * familiarisation sessions are excluded from the baseline
  * baseline = rolling median of the most recent valid sessions, so it follows
    the person's slow learning trend instead of a fixed early average
  * only DECLINES are flagged; getting better never triggers anything
"""
import statistics as st

import config as C

ADVICE = {
    "hand_eye": "Avoid fine manual control tasks (robotic arm, docking, piloting) or work with a second operator.",
    "memory": "Use written checklists; don't rely on remembering positions or sequences today.",
    "attention": "Avoid long monitoring tasks; take breaks and double-check readings.",
}


NAMES = {"hand_eye": "Hand-eye", "memory": "Memory", "attention": "Attention"}


def _num(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def _fmt(x):
    return f"{x:.0f}" if abs(x) >= 10 else f"{x:.2f}".rstrip("0").rstrip(".")


def build_baseline(history):
    use = [h for h in history
           if str(h.get("invalid", "0")) in ("0", "False", "")
           and (_num(h.get("session_index")) or 0) > C.FAMILIARISATION_SESSIONS
           and h.get("data_source") != "practice"][-C.BASELINE_MAX_SESSIONS:]
    if len(use) < C.BASELINE_MIN_SESSIONS:
        return None
    b = {"n": len(use), "n_simulated": sum(1 for h in use if h.get("data_source") == "simulated")}
    for key, _dir, floor, *_ in C.METRICS:
        v = [x for x in (_num(h.get(key)) for h in use) if x is not None]
        if len(v) >= C.BASELINE_MIN_SESSIONS:
            c = st.median(v)
            b[key] = {"centre": c, "spread": max(1.4826 * st.median([abs(x - c) for x in v]), floor)}
    return b


def evaluate(scores, checkin, history, session_index):
    base = build_baseline(history)
    comp = {c: {"status": "normal", "reasons": []} for c in C.COMPONENTS}
    detail = {}

    # data quality
    quality = []
    if (scores.get("t1_timeouts") or 0) >= 3:
        quality.append(f"{scores['t1_timeouts']} port rounds timed out")
    if scores.get("t3_on_target_pct") is not None and scores["t3_on_target_pct"] < 10:
        quality.append("laser almost never on target (not tracking)")
    invalid = bool(quality)

    for key, direction, floor, generic, component, label in C.METRICS:
        v = _num(scores.get(key))
        if v is None:
            continue
        if base and key in base:
            c, s = base[key]["centre"], base[key]["spread"]
            z = (v - c) / s * direction          # positive = worse
            detail[key] = {"value": v, "normal": c, "z": z}
            if z > C.Z_FLAG:
                comp[component]["status"] = "slower"
                comp[component]["reasons"].append(f"{label}: {_fmt(v)} vs your normal ~{_fmt(c)}")
        else:
            bad = v > generic if direction > 0 else v < generic
            detail[key] = {"value": v, "normal": None, "z": None}
            if bad:
                comp[component]["status"] = "slower"
                comp[component]["reasons"].append(f"{label}: {_fmt(v)} (generic limit {_fmt(generic)})")

    slower = [c for c in C.COMPONENTS if comp[c]["status"] == "slower"]
    sleep, fat, stress = _num(checkin.get("sleep_hours")), _num(checkin.get("fatigue")), _num(checkin.get("stress"))
    context = []
    if sleep is not None and sleep < C.SHORT_SLEEP_H:
        context.append(f"short sleep ({sleep:g} h)")
    if fat is not None and fat >= C.HIGH_FATIGUE:
        context.append(f"high fatigue ({fat:.0f}/7)")
    tired = bool(context)
    if stress is not None and stress >= 4:
        context.append(f"high stress ({stress:.0f}/5)")

    if invalid:
        status, head = "RETEST", "Session not reliable - please retest"
        msg = "Data-quality checks failed; this shift is not used for a decision or for your baseline."
    elif slower and tired:
        status, head = "NO-GO", "Avoid safety-critical manual tasks today"
        msg = f"{', '.join(NAMES[s] for s in slower)} below your normal AND {' and '.join(c for c in context if 'stress' not in c)}. Inform crew lead / flight surgeon; retest after rest."
    elif slower:
        status, head = "CAUTION", "Below your normal - retest in 2-4 h"
        msg = f"{', '.join(NAMES[s] for s in slower)} below your normal without a sleep/fatigue explanation."
    elif tired:
        status, head = "CAUTION", "Scores nominal, but running on low sleep"
        msg = "Performance is fine now; fatigue often catches up later. Retest before critical tasks."
    else:
        status, head = "GO", "All components nominal"
        msg = "Hand-eye, memory and attention are within your normal range." if base else \
              "No concerns against generic limits. Personal baseline still forming."
    advice = [ADVICE[c] for c in slower] if status in ("NO-GO", "CAUTION") else []

    if invalid:
        conf, why = "LOW", "data-quality problems"
    elif base and base["n"] >= C.HIGH_CONFIDENCE_SESSIONS:
        conf, why = "HIGH", f"personal baseline, {base['n']} sessions"
    elif base:
        conf, why = "MEDIUM", f"baseline forming, {base['n']} sessions"
    elif session_index <= C.FAMILIARISATION_SESSIONS:
        conf, why = "LOW", f"familiarisation {session_index}/{C.FAMILIARISATION_SESSIONS}"
    else:
        conf, why = "LOW", "generic limits used"
    if base and base["n_simulated"]:
        why += f" ({base['n_simulated']} SIMULATED)"
    mode = (f"personal_n{base['n']}" + (f"_sim{base['n_simulated']}" if base["n_simulated"] else "")) if base else "generic"
    if session_index <= C.FAMILIARISATION_SESSIONS:
        mode += "_familiarisation"
    return {"status": status, "headline": head, "message": msg, "advice": advice, "confidence": conf,
            "confidence_why": why, "components": comp, "detail": detail, "context": context,
            "quality": quality, "invalid": invalid, "baseline": base, "baseline_mode": mode}
