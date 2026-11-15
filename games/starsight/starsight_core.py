"""
STARSIGHT core logic (no graphics). Python port of the web prototype's logic.js:
same rules, same scoring, same decisions, same CSV columns.

Round 1  GHOST SIGNALS  - contrast sensitivity (how faint a striped pattern you can see)
Round 2  SHARP SHOOTER  - near vision (smallest Tumbling-E you can read at 40 cm), in logMAR
Each round runs for the right eye, then the left eye.
logMAR: 0.0 = normal (20/20), 0.3 = 20/40, 1.0 = 20/200. LOWER is better.
"""

import csv
import io
import math
import random
import statistics
from datetime import datetime, timedelta

VCFG = {
    "VERSION": "starsight-py-2.0",
    # Round 1: GHOST SIGNALS
    "CS_FREQS": [("wide", 1.5), ("fine", 4.0)],          # cycles per degree
    "CS_FADE_RATE": 0.30, "CS_MIN": 0.004, "CS_CONFIRM": 6, "CS_WARMUP": 0.20, "CS_START_OFFSET": 0.5,
    "CS_STEP_HARDER": 0.10, "CS_STEP_EASIER": 0.20, "CS_SHOW_S": 1.5, "CS_TIMEOUT_S": 4.0, "CS_GAP_S": 0.7,
    "CS_SIDE_DEG": 6.0, "CS_PATCH_DEG": 4.0, "CS_SIGMA_DEG": 0.8,
    "CS_TYPICAL": {"wide": 1.7, "fine": 1.8},
    # Round 2: SHARP SHOOTER (near vision, Tumbling E at reading distance)
    "SS_DIST_MM": 400, "SS_START": 0.8, "SS_WARMUP": 2, "SS_TRIALS": 12, "SS_STEP_HARDER": 0.1, "SS_STEP_EASIER": 0.2,
    "SS_MIN_LOGMAR": -0.3, "SS_MAX_LOGMAR": 1.2, "SS_TIMEOUT_S": 6.0, "SS_GAP_S": 0.45, "SS_TYPICAL": 0.0,
    # decisions
    "QUEASY_MAX": 3, "BASELINE_MIN": 3, "BASELINE_MAX": 10, "CS_DROP": 0.25, "NA_WORSE": 0.2,
    "GENERIC_CS_LOW": 1.3, "GENERIC_NA_HIGH": 0.5,
}
C = VCFG


def clamp_log(l):
    return max(math.log10(C["CS_MIN"]), min(0.0, l))


def r2(x):
    return None if x is None else round(x, 2)


# ===================================================================== Round 1
class FadeTrial:
    kind = "fade"

    def __init__(self, label, freq):
        self.label, self.freq, self.tapped = label, freq, None

    @property
    def dur(self):
        return abs(math.log10(C["CS_MIN"])) / C["CS_FADE_RATE"] + 0.5

    def contrast_at(self, t):
        return max(C["CS_MIN"], 10 ** (-C["CS_FADE_RATE"] * t))

    def stim(self, t):
        return None if self.tapped is not None else {"freq": self.freq, "contrast": self.contrast_at(t), "side": "center"}

    def tap(self, t, side=None):
        if self.tapped is None:
            self.tapped = self.contrast_at(t)

    def finished(self, t):
        return self.tapped is not None or t >= self.dur


class SideTrial:
    kind = "side"

    def __init__(self, label, freq, contrast, side, warmup):
        self.label, self.freq, self.contrast, self.side, self.warmup = label, freq, contrast, side, warmup
        self.answer = None

    def stim(self, t):
        return {"freq": self.freq, "contrast": self.contrast, "side": self.side} if t < C["CS_SHOW_S"] else None

    def tap(self, t, side=None):
        if self.answer is None and side in ("left", "right"):
            self.answer = side

    def finished(self, t):
        return self.answer is not None or t >= C["CS_TIMEOUT_S"]

    @property
    def correct(self):
        return self.answer == self.side


class ContrastTest:
    def __init__(self, eye, rng=None):
        self.eye, self.rng = eye, rng or random.Random()
        self.trials, self.done, self.in_gap = [], False, True
        self.gap_start = self.trial_start = 0.0
        self.fi = self.cn = 0
        self.level = self.fade_level = None
        self.total = len(C["CS_FREQS"]) * (1 + C["CS_CONFIRM"])

    @property
    def current(self):
        return self.trials[-1] if self.trials else None

    @property
    def progress(self):
        return min(1.0, len(self.trials) / self.total)

    def _next(self):
        if self.fi >= len(C["CS_FREQS"]):
            return None
        label, freq = C["CS_FREQS"][self.fi]
        last = self.current
        if last is None or (last.kind == "side" and self.cn >= C["CS_CONFIRM"]):
            if last is not None:
                self.fi += 1
                self.cn = 0
                if self.fi >= len(C["CS_FREQS"]):
                    return None
                label, freq = C["CS_FREQS"][self.fi]
            return FadeTrial(label, freq)
        warm = False
        if last.kind == "fade":
            self.fade_level = math.log10(last.tapped or C["CS_MIN"])
            self.level = clamp_log(math.log10(max(C["CS_WARMUP"], 10 ** (self.fade_level + 0.8))))
            warm = True
        elif self.cn == 1:
            self.level = clamp_log(self.fade_level + C["CS_START_OFFSET"])
        else:
            self.level = clamp_log(self.level + (-C["CS_STEP_HARDER"] if last.correct else C["CS_STEP_EASIER"]))
        self.cn += 1
        return SideTrial(label, freq, 10 ** self.level, "left" if self.rng.random() < 0.5 else "right", warm)

    def update(self, now):
        if self.done:
            return
        if self.in_gap:
            if now - self.gap_start >= C["CS_GAP_S"]:
                n = self._next()
                if n is None:
                    self.done = True
                    return
                self.trials.append(n)
                self.trial_start, self.in_gap = now, False
            return
        if self.current.finished(now - self.trial_start):
            self.in_gap, self.gap_start = True, now

    def tap(self, now, side=None):
        if not self.done and not self.in_gap and self.current:
            self.current.tap(now - self.trial_start, side)

    def stim(self, now):
        if self.done or self.in_gap or not self.current:
            return None
        return self.current.stim(now - self.trial_start)

    def waiting_for_side(self):
        return (not self.in_gap) and self.current is not None and self.current.kind == "side" and self.current.answer is None

    def status_text(self):
        cur = self.current
        if self.done:
            return ""
        if self.in_gap or cur is None:
            return "get ready..."
        if cur.kind == "fade":
            return f"{cur.label.upper()} SIGNAL FADING: tap when it's gone"
        return f"{cur.label.upper()} SIGNAL: which porthole?" + (" (warm-up)" if cur.warmup else "")

    def results(self):
        out, per, reasons = {"eye": self.eye}, [], []
        for label, _ in C["CS_FREQS"]:
            fades = [t for t in self.trials if t.kind == "fade" and t.label == label]
            sides = [t for t in self.trials if t.kind == "side" and t.label == label and not t.warmup]
            if not sides:
                out["cs_" + label] = None
                continue
            last = sides[-4:]
            v = r2(-sum(math.log10(t.contrast) for t in last) / len(last))
            out["cs_" + label] = v
            per.append(v)
            acc = sum(t.correct for t in sides) / len(sides)
            if acc <= 0.5:
                reasons.append(f"{label} signals: answers no better than guessing")
            if fades and fades[0].tapped and abs(-math.log10(fades[0].tapped) - v) > 0.6:
                reasons.append(f"{label} signals: fade and side answers disagree")
        out["cs_mean"] = r2(sum(per) / len(per)) if per else None
        out["cs_quality"] = "ok" if per and not reasons else "unreliable"
        out["cs_reason"] = "; ".join(reasons)
        return out


# ===================================================================== Round 2
class ETrial:
    """One Tumbling-E target. level = requested logMAR, shown = logMAR actually drawn (screen pixels round it)."""
    kind = "e"

    def __init__(self, level, shown, direction, warmup, at_floor):
        self.level, self.shown, self.direction, self.warmup, self.at_floor = level, shown, direction, warmup, at_floor
        self.answer = None

    def tap(self, t, direction=None):
        if self.answer is None and direction in DIRS:
            self.answer = direction

    def finished(self, t):
        return self.answer is not None or t >= C["SS_TIMEOUT_S"]

    @property
    def correct(self):
        return self.answer == self.direction


DIRS = ("up", "down", "left", "right")


class SharpTest:
    """SHARP SHOOTER: near-vision Tumbling E at reading distance (40 cm).
    Staircase: hit -> 0.1 logMAR smaller, miss -> 0.2 bigger (aims at ~67% correct; guessing = 25%).
    quantize(logmar) -> (logmar_actually_drawn, at_screen_limit) is supplied by the app (pixel rounding)."""

    def __init__(self, eye, quantize=None, rng=None):
        self.eye, self.rng = eye, rng or random.Random()
        self.quantize = quantize or (lambda lm: (max(lm, C["SS_MIN_LOGMAR"]), lm <= C["SS_MIN_LOGMAR"]))
        self.trials, self.done, self.in_gap, self.gap_start, self.trial_start = [], False, True, 0.0, 0.0
        self.level, self.combo, self.best = C["SS_START"], 0, None
        self.total = C["SS_WARMUP"] + C["SS_TRIALS"]

    @property
    def current(self):
        return self.trials[-1] if self.trials else None

    @property
    def progress(self):
        return min(1.0, len(self.trials) / self.total)

    def _next(self):
        n = len(self.trials)
        if n >= self.total:
            return None
        last = self.current
        if last is not None and n > C["SS_WARMUP"]:
            self.level = self.level - C["SS_STEP_HARDER"] if last.correct else self.level + C["SS_STEP_EASIER"]
        self.level = max(C["SS_MIN_LOGMAR"], min(C["SS_MAX_LOGMAR"], self.level))
        shown, floor = self.quantize(self.level)
        prev = last.direction if last else None
        d = self.rng.choice([x for x in DIRS if x != prev])
        return ETrial(self.level, shown, d, n < C["SS_WARMUP"], floor)

    def update(self, now):
        if self.done:
            return
        if self.in_gap:
            if now - self.gap_start >= C["SS_GAP_S"]:
                nxt = self._next()
                if nxt is None:
                    self.done = True
                    return
                self.trials.append(nxt)
                self.trial_start, self.in_gap = now, False
            return
        if self.current.finished(now - self.trial_start):
            tr = self.current
            if tr.correct:
                self.combo += 1
                if not tr.warmup:
                    self.best = tr.shown if self.best is None else min(self.best, tr.shown)
            else:
                self.combo = 0
            self.in_gap, self.gap_start = True, now

    def tap(self, now, direction=None):
        if not self.done and not self.in_gap and self.current:
            self.current.tap(now - self.trial_start, direction)

    def target(self):
        return None if (self.done or self.in_gap or not self.current) else self.current

    def status_text(self):
        cur = self.current
        if self.done:
            return ""
        if self.in_gap or cur is None:
            return "next target incoming..."
        return ("WARM-UP TARGET: " if cur.warmup else "") + "which way do the arms point?"

    def results(self):
        warm = [t for t in self.trials if t.warmup]
        scored = [t for t in self.trials if not t.warmup]
        r = {"eye": self.eye}
        if not scored:
            r.update(na_logmar=None, na_snellen=None, na_floor=0, na_best=None, na_quality="unreliable", na_reason="no answers")
            return r
        last = scored[-6:]
        lm = r2(sum(t.shown for t in last) / len(last))
        acc = sum(t.correct for t in scored) / len(scored)
        floor = 1 if sum(t.at_floor for t in last) >= 3 and acc >= 0.6 else 0
        reasons = []
        if sum(t.correct for t in warm) < len(warm):
            reasons.append("missed an easy warm-up target")
        if acc <= 0.35:
            reasons.append("answers no better than guessing")
        r.update(na_logmar=lm, na_snellen=int(round(20 * 10 ** lm)), na_floor=floor, na_best=r2(self.best),
                 na_accuracy=round(acc, 2), na_quality="unreliable" if reasons else "ok", na_reason=", ".join(reasons))
        return r


# ===================================================================== simulation
class SimViewer:
    """Fake astronaut: known contrast thresholds (logCS) and near-vision threshold (logMAR)."""

    def __init__(self, cs=None, na=0.05, rng=None):
        self.cs = cs or dict(C["CS_TYPICAL"])
        self.na, self.rng = na, rng or random.Random()
        self.lag = 0.3
        self.trial = self.plan = None

    def step_cs(self, test, now):
        tr = None if test.in_gap else test.current
        if tr is not self.trial:
            self.trial, self.plan = tr, None
            if tr is not None and tr.kind == "side":
                thr = 10 ** (-self.cs[tr.label])
                seen = self.rng.random() < 1 - math.exp(-((tr.contrast / thr) ** 3))
                self.plan = [now + 0.6 + self.rng.random() * 0.4, tr.side if seen else self.rng.choice(["left", "right"])]
        if tr is None:
            return False, None
        if tr.kind == "fade" and self.plan is None and tr.contrast_at(now - test.trial_start) < 10 ** (-self.cs[tr.label]):
            self.plan = [now + self.lag, None]
        if self.plan and now >= self.plan[0]:
            p, self.plan = self.plan, [float("inf"), None]
            return True, p[1]
        return False, None

    def step_na(self, test, now):
        tr = test.target()
        if tr is not self.trial:
            self.trial, self.plan = tr, None
            if tr is not None:
                p = 0.25 + 0.75 * (1 - math.exp(-((10 ** (tr.shown - self.na)) ** 4)))
                ok = self.rng.random() < p
                self.plan = [now + 0.7 + self.rng.random() * 0.5, tr.direction if ok else self.rng.choice([d for d in DIRS if d != tr.direction])]
        if self.plan and tr is not None and now >= self.plan[0]:
            p, self.plan = self.plan, [float("inf"), None]
            return True, p[1]
        return False, None


def simulate_eye(eye, viewer, quantize=None):
    c, t = ContrastTest(eye, viewer.rng), 0.0
    while not c.done:
        c.update(t)
        tap, side = viewer.step_cs(c, t)
        if tap:
            c.tap(t, side)
        t += 1 / 60
    viewer.trial = None
    s, t = SharpTest(eye, quantize, viewer.rng), 0.0
    while not s.done:
        s.update(t)
        tap, d = viewer.step_na(s, t)
        if tap:
            s.tap(t, d)
        t += 1 / 60
    return {**c.results(), **s.results()}


# ===================================================================== rows + decisions
VCOLS = ["crew", "session", "timestamp", "data_source", "version", "queasy", "glasses", "valid", "status",
         "cs_wide_R", "cs_fine_R", "cs_mean_R", "cs_quality_R", "na_logmar_R", "na_snellen_R", "na_floor_R", "na_quality_R",
         "cs_wide_L", "cs_fine_L", "cs_mean_L", "cs_quality_L", "na_logmar_L", "na_snellen_L", "na_floor_L", "na_quality_L",
         "eye_gap_cs", "eye_gap_na", "vision_score"]
_ROW_KEYS = ["cs_wide", "cs_fine", "cs_mean", "cs_quality", "cs_reason", "na_logmar", "na_snellen", "na_floor", "na_best",
             "na_quality", "na_reason"]


def build_row(R, L, meta):
    row = dict(meta)
    for e, x in (("R", R), ("L", L)):
        for k in _ROW_KEYS:
            row[f"{k}_{e}"] = x.get(k)
    both = lambda k: R.get(k) is not None and L.get(k) is not None
    row["eye_gap_cs"] = r2(abs(R["cs_mean"] - L["cs_mean"])) if both("cs_mean") else None
    row["eye_gap_na"] = r2(abs(R["na_logmar"] - L["na_logmar"])) if both("na_logmar") else None
    row["vision_score"] = r2((R["cs_mean"] + L["cs_mean"]) / 2) if both("cs_mean") else None
    all_ok = all(q == "ok" for q in (R.get("cs_quality"), L.get("cs_quality"), R.get("na_quality"), L.get("na_quality")))
    row["valid"] = 1 if all_ok and (meta.get("queasy") or 0) <= C["QUEASY_MAX"] else 0
    return row


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def vision_baseline(history):
    use = [h for h in history if int(h.get("valid", 0) or 0) == 1 and h.get("data_source") != "practice"][-C["BASELINE_MAX"]:]
    if len(use) < C["BASELINE_MIN"]:
        return None
    b = {"n": len(use), "n_sim": sum(1 for h in use if h.get("data_source") == "simulated")}
    for k in ("cs_mean_R", "cs_mean_L", "na_logmar_R", "na_logmar_L"):
        v = [x for x in (_num(h.get(k)) for h in use) if x is not None]
        if len(v) >= C["BASELINE_MIN"]:
            b[k] = statistics.median(v)
    return b


def snellen(lm):
    return None if lm is None else f"20/{int(round(20 * 10 ** lm))}"


def evaluate_vision(row, history):
    base, notes = vision_baseline(history), []
    flags = {"R": [], "L": []}          # (kind, text)  kind: "cs" (faintness) or "na" (near vision)
    eye_name = {"R": "RIGHT", "L": "LEFT"}
    if (row.get("queasy") or 0) > C["QUEASY_MAX"]:
        notes.append(f"you reported feeling queasy ({row['queasy']}/10): nausea makes vision tests unreliable")
    for e in ("R", "L"):
        if row.get(f"cs_quality_{e}") != "ok":
            notes.append(f"{eye_name[e]} eye, Ghost Signals: {row.get(f'cs_reason_{e}') or 'unreliable'}")
        if row.get(f"na_quality_{e}") != "ok":
            notes.append(f"{eye_name[e]} eye, Sharp Shooter: {row.get(f'na_reason_{e}') or 'unreliable'}")
        if row.get(f"na_floor_{e}"):
            notes.append(f"{eye_name[e]} eye reached this screen's smallest letter: real near vision may be even sharper")
    if base:
        mode = "personal"
        for e in ("R", "L"):
            cs, bc = row.get(f"cs_mean_{e}"), base.get(f"cs_mean_{e}")
            if cs is not None and bc is not None and bc - cs >= C["CS_DROP"]:
                flags[e].append(("cs", f"faint-vision score dropped {r2(bc - cs)} log units vs your normal ({r2(bc)} -> {cs})"))
            na, bn = row.get(f"na_logmar_{e}"), base.get(f"na_logmar_{e}")
            if na is not None and bn is not None and na - bn >= C["NA_WORSE"]:
                flags[e].append(("na", f"near vision {round((na - bn) * 10)} lines worse than your normal ({snellen(bn)} -> {snellen(na)})"))
    else:
        mode = "generic"
        for e in ("R", "L"):
            cs, na = row.get(f"cs_mean_{e}"), row.get(f"na_logmar_{e}")
            if cs is not None and cs < C["GENERIC_CS_LOW"]:
                flags[e].append(("cs", f"faint-vision score {cs} is below the rough screen reference ({C['GENERIC_CS_LOW']})"))
            if na is not None and na > C["GENERIC_NA_HIGH"]:
                flags[e].append(("na", f"near vision {snellen(na)} is blurrier than the rough reference ({snellen(C['GENERIC_NA_HIGH'])})"))
    cs_eyes = [e for e in ("R", "L") if any(k == "cs" for k, _ in flags[e])]
    na_eyes = [e for e in ("R", "L") if any(k == "na" for k, _ in flags[e])]
    names = lambda es: " and ".join(eye_name[e] for e in es)
    if not row["valid"]:
        status, headline, message = "RETEST", "Not reliable today: retest", "This check is greyed out and won't be used for your baseline."
    elif mode == "personal" and cs_eyes:
        status, headline = "SCAN NOW", f"Request an eye scan (OCT) for the {names(cs_eyes)} eye"
        message = (f"Only the {eye_name[cs_eyes[0]]} eye lost faint vision, while the other eye stayed normal. Screen or lighting "
                   "problems would affect both eyes, so this looks like a real eye change. Don't wait for the next scheduled exam."
                   if len(cs_eyes) == 1 else
                   "Both eyes lost faint vision. Retest once in better conditions; if it repeats, request an eye scan.")
        if na_eyes:
            message += f" Near vision is also worse in the {names(na_eyes)} eye: try your space anticipation glasses."
    elif mode == "personal" and na_eyes:
        status, headline = "GLASSES", f"Near vision worse in the {names(na_eyes)} eye"
        message = ("Close-up blur is the most common SANS change. Try your space anticipation glasses (reading glasses for space) "
                   "and retest tomorrow. If it keeps getting worse, tell the flight surgeon.")
    elif cs_eyes or na_eyes:
        status, headline = "CHECK", "Outside the rough reference: retest tomorrow"
        message = "Your personal baseline isn't ready yet, so this compares you with rough screen values only. If it repeats, tell the flight surgeon."
    else:
        status = "GO"
        headline = "Both eyes match your normal" if base else "Looks fine: your baseline is still forming"
        valid_n = sum(1 for h in history if int(h.get("valid", 0) or 0) == 1) + 1
        message = ("Faint vision and near vision are within your usual range." if base
                   else f"Valid scans so far: {valid_n}/{C['BASELINE_MIN']} before your personal baseline turns on.")
    confidence = "LOW" if not row["valid"] else ("HIGH" if base and base["n"] >= 5 else "MEDIUM" if base else "LOW")
    why = ("unreliable session" if not row["valid"] else
           f"personal baseline from {base['n']} sessions" + (f" ({base['n_sim']} SIMULATED)" if base["n_sim"] else "") if base
           else "no personal baseline yet")
    return {"status": status, "headline": headline, "message": message, "flags": {e: [t for _, t in flags[e]] for e in flags},
            "flag_kinds": flags, "notes": notes, "mode": mode, "base": base, "confidence": confidence, "why": why}


def make_demo_history(crew, n=6, rng=None, quantize=None):
    """6 simulated healthy days, played by the simulated astronaut on THIS screen (so screen limits are realistic)."""
    rng = rng or random.Random()
    rows, start = [], datetime.now() - timedelta(days=n + 1)
    for i in range(1, n + 1):
        R = simulate_eye("right", SimViewer(na=0.05, rng=rng), quantize)
        L = simulate_eye("left", SimViewer(na=0.03, rng=rng), quantize)
        d = (start + timedelta(days=i)).replace(hour=8, minute=0, second=0, microsecond=0)
        row = build_row(R, L, {"crew": crew, "session": i, "timestamp": d.isoformat(timespec="seconds"),
                               "data_source": "simulated", "queasy": 0, "glasses": "yes", "version": C["VERSION"]})
        row["status"] = "GO"
        rows.append(row)
    return rows


DEMO_RIGHT = {"cs": {"wide": 1.25, "fine": 1.3}, "na": 0.65}   # simulated day-140 right eye (SANS-like)


def to_csv(rows, cols=VCOLS):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return buf.getvalue()


if __name__ == "__main__":
    rng = random.Random(1)
    for na in (0.0, 0.3):
        a = [simulate_eye("right", SimViewer(na=na, rng=rng)) for _ in range(40)]
        lm = [x["na_logmar"] for x in a]
        print(f"near-vision true {na:+.2f} -> measured mean {statistics.mean(lm):+.3f} sd {statistics.pstdev(lm):.3f} | "
              f"logCS {statistics.mean(x['cs_mean'] for x in a):.2f} | unreliable {sum(1 for x in a if x['cs_quality'] != 'ok' or x['na_quality'] != 'ok')}")
    hist = make_demo_history("AST-01", rng=rng)
    R = simulate_eye("right", SimViewer(DEMO_RIGHT["cs"], DEMO_RIGHT["na"], rng=rng))
    L = simulate_eye("left", SimViewer(rng=rng))
    row = build_row(R, L, {"crew": "AST-01", "session": 7, "data_source": "simulated", "queasy": 0, "glasses": "yes"})
    ev = evaluate_vision(row, hist)
    print(ev["status"], "|", ev["headline"])
    for f in ev["flags"]["R"]:
        print("  RIGHT:", f)
    # near-only change
    R2 = simulate_eye("right", SimViewer(na=0.4, rng=rng))
    row2 = build_row(R2, simulate_eye("left", SimViewer(rng=rng)), {"crew": "AST-01", "session": 8, "data_source": "simulated", "queasy": 0})
    print(evaluate_vision(row2, hist)["status"])
