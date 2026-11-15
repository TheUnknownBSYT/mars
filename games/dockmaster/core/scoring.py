"""
Events -> scores. Pure Python.
Task 1 click  : task=1, kind="click", round, expected, clicked (number or 0 = empty space), correct, dt_ms, err_px, first
Task 1 round  : task=1, kind="round", round, perfect, timeout, first_click_ms
Task 2 pick   : task=2, kind="pick", round, correct, time_ms, err_px
Task 2 round  : task=2, kind="round", round, n_correct, timeout
Task 3 round  : task=3, kind="beam", round, track_err_px, on_target_pct, greens, answer, count_err, answer_ms
"""
import statistics as st


def _med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None


def _mean(v):
    v = [x for x in v if x is not None]
    return st.fmean(v) if v else None


def _r(x, nd=0):
    if x is None:
        return None
    return round(x, nd) if nd else int(round(x))


def score_ports(ev):
    clicks = [e for e in ev if e["kind"] == "click"]
    rounds = [e for e in ev if e["kind"] == "round"]
    on_port = [e for e in clicks if e["clicked"]]
    return {
        "t1_order_acc": _r(sum(e["correct"] for e in clicks) / len(clicks), 3) if clicks else None,
        "t1_perfect_rounds": sum(r["perfect"] for r in rounds),
        "t1_rounds": len(rounds),
        "t1_timeouts": sum(r["timeout"] for r in rounds),
        "t1_first_click_ms": _r(_med([r["first_click_ms"] for r in rounds])),
        "t1_click_time_ms": _r(_med([e["dt_ms"] for e in clicks if not e["first"]])),
        "t1_click_err_px": _r(_med([e["err_px"] for e in on_port]), 1),
        "t1_empty_clicks": sum(1 for e in clicks if not e["clicked"]),
    }


def score_track(ev):
    picks = [e for e in ev if e["kind"] == "pick"]
    rounds = [e for e in ev if e["kind"] == "round"]
    total = sum(r.get("n_targets", 2) for r in rounds) or 1
    return {
        "t2_correct": sum(p["correct"] for p in picks),
        "t2_accuracy": _r(sum(p["correct"] for p in picks) / total, 3) if rounds else None,
        "t2_perfect_rounds": sum(1 for r in rounds if r["n_correct"] == r.get("n_targets", 2)),
        "t2_rounds": len(rounds),
        "t2_select_time_ms": _r(_med([p["time_ms"] for p in picks])),
        "t2_click_err_px": _r(_med([p["err_px"] for p in picks]), 1),
        "t2_timeouts": sum(r["timeout"] for r in rounds),
    }


def score_beam(ev):
    b = [e for e in ev if e["kind"] == "beam"]
    return {
        "t3_track_err_px": _r(_mean([e["track_err_px"] for e in b]), 1),
        "t3_on_target_pct": _r(_mean([e["on_target_pct"] for e in b]), 1),
        "t3_count_err": sum(e["count_err"] for e in b) if b else None,
        "t3_count_correct": sum(1 for e in b if e["count_err"] == 0),
        "t3_rounds": len(b),
        "t3_answer_ms": _r(_med([e["answer_ms"] for e in b])),
    }


def score_session(e1, e2, e3):
    out = {}
    out.update(score_ports(e1))
    out.update(score_track(e2))
    out.update(score_beam(e3))
    return out
