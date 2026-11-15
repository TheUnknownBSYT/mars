"""
COMMS CHECK - core logic (no pygame). Used by comms_app.py.

The game is a digits-in-noise hearing test: three spoken digits play in ONE earphone over radio static.
If the player decodes all three, the next code gets MORE static; if not, LESS. That staircase homes in on
the "speech reception threshold" (SRT): how loud the static can be, compared with the voice, before you can
only decode about half the codes. Lower (more negative) SRT = better hearing in noise.

Each ear is compared with ITS OWN normal (median of past valid scans) and with the other ear.
Screening / education prototype - not a medical device, not validated.
"""

import csv
import io
import math
import random
from datetime import datetime, timedelta

import numpy as np

CFG = {
    "VERSION": "commscheck-py-1.2",
    # staircase (dB SNR = voice level minus static level)
    "WARMUP_SNR": 12.0,       # first code is easy: checks volume + the right earphone works
    "START_SNR": 6.0,         # start clear, then the static creeps up
    "TRIALS": 12,             # per ear, warm-up included  (~70 s per ear)
    "STEP_FAST": 4.0,         # big steps until the first miss
    "STEP": 2.0,
    "MIN_SNR": -20.0, "MAX_SNR": 12.0,
    "SRT_LAST": 8,            # SRT = mean SNR of the last 8 scored codes + the level that would come next
    "RESP_TIMEOUT_S": 9.0,    # time to type after the code ends
    "GAP_S": 0.8,             # pause between codes
    "DIGITS": "012345689",             # 7 left out: "seven" is the only two-syllable digit (easier to spot)
    # audio layout
    "LEAD_S": 0.5, "DIGIT_GAP_S": 0.32, "TAIL_S": 0.4,
    "SPEECH_RMS": 0.16,       # the voice is ALWAYS this loud; only the static moves up and down
    # decisions
    "BASELINE_MIN": 3, "BASELINE_MAX": 10,
    "SRT_WORSE": 3.0,         # one ear >= 3 dB worse than its own normal -> HEARING CHECK
    "GAP_FLAG": 4.0,          # left vs right differ by >= 4 dB (no baseline yet) -> CHECK
    "GENERIC_SRT_HIGH": -4.0, # rough reference only (real values depend on the voice + headphones)
    "TYPICAL_SRT": -9.0,      # rough "typical" marker for the meter
}


def r1(x):
    return None if x is None else round(float(x), 1)


# ============================================================ one ear
class Trial:
    def __init__(self, snr, digits, warmup):
        self.snr, self.digits, self.warmup = snr, digits, warmup
        self.answer = None        # string typed, or "" on timeout
        self.timed_out = False

    @property
    def correct(self):
        return self.answer == self.digits

    @property
    def digits_right(self):
        a = self.answer or ""
        return sum(1 for i, d in enumerate(self.digits) if i < len(a) and a[i] == d)


class DigitsTest:
    """Adaptive digits-in-noise staircase for one ear. The UI calls next_trial(), plays it, then answer()."""

    def __init__(self, ear, rng=None):
        self.ear, self.rng = ear, rng or random.Random()
        self.trials, self.snr, self.fast, self.combo, self.best = [], CFG["START_SNR"], True, 0, None

    @property
    def progress(self):
        return min(1.0, len(self.trials) / CFG["TRIALS"])

    @property
    def done(self):
        return len(self.trials) >= CFG["TRIALS"] and self.trials[-1].answer is not None

    def _code(self):
        pool = CFG["DIGITS"]
        last = self.trials[-1].digits if self.trials else ""
        while True:
            d = "".join(self.rng.sample(pool, 3))        # no digit repeated inside a code
            if d != last:
                return d

    def next_trial(self):
        if len(self.trials) >= CFG["TRIALS"]:
            return None
        warm = not self.trials
        tr = Trial(CFG["WARMUP_SNR"] if warm else round(self.snr, 1), self._code(), warm)
        self.trials.append(tr)
        return tr

    def answer(self, trial, typed, timed_out=False):
        trial.answer, trial.timed_out = typed, timed_out
        if trial.correct:
            self.combo += 1
            if not trial.warmup:
                self.best = trial.snr if self.best is None else min(self.best, trial.snr)
        else:
            self.combo = 0
        if not trial.warmup:
            if not trial.correct:
                self.fast = False
            step = CFG["STEP_FAST"] if self.fast else CFG["STEP"]
            self.snr += -step if trial.correct else step
            self.snr = max(CFG["MIN_SNR"], min(CFG["MAX_SNR"], self.snr))
        return trial.correct

    def results(self):
        e = self.ear[0].upper()
        sc = [t for t in self.trials if not t.warmup and t.answer is not None]
        warm = [t for t in self.trials if t.warmup]
        out = {"ear": self.ear}
        if len(sc) < 4:
            return {**out, "srt": None, "quality": "unreliable", "reason": "not enough codes answered",
                    "digit_acc": None, "codes_ok": 0, "best": None, "floor": 0}
        lev = [t.snr for t in sc[-CFG["SRT_LAST"]:]] + [self.snr]
        srt = sum(lev) / len(lev)
        dacc = sum(t.digits_right for t in sc) / (3 * len(sc))
        reasons = []
        if warm and not warm[0].correct:
            reasons.append("missed the easy warm-up code (volume too low, or wrong earphone?)")
        if sum(t.timed_out for t in sc) >= 3:
            reasons.append("several codes not answered in time")
        if dacc < 0.45:
            reasons.append("most digits wrong, even when the voice was loud")
        if srt >= CFG["MAX_SNR"] - 2:
            reasons.append("couldn't decode even the clearest codes")
        floor = 1 if srt <= CFG["MIN_SNR"] + 2 else 0
        return {**out, "srt": r1(srt), "quality": "unreliable" if reasons else "ok", "reason": "; ".join(reasons),
                "digit_acc": round(dacc, 2), "codes_ok": sum(t.correct for t in sc), "best": self.best, "floor": floor}


# ============================================================ audio (numpy only)
def _trim(x, sr):
    a = np.convolve(np.abs(x), np.ones(64) / 64, "same")        # smoothed loudness
    thr = max(a.max() * 0.004, 1e-5)                              # -48 dB: keeps the quiet ends of words ("six", "eight")
    idx = np.where(a > thr)[0]
    if not len(idx):
        return x
    return x[max(0, idx[0] - int(0.03 * sr)): min(len(x), idx[-1] + int(0.08 * sr))]


def _rms_active(x):
    a = np.abs(x)
    act = x[a > a.max() * 0.1] if a.max() > 0 else x
    return float(np.sqrt(np.mean(act ** 2))) if len(act) else 1.0


class Voice:
    """Ten digit recordings, levelled to the same loudness, plus 'speech-shaped' static made from their spectrum
    (static with the same pitch balance as the voice, like the real digits-in-noise test)."""

    def __init__(self, waves, sr):
        self.sr = sr
        self.digits = {}
        for d, w in waves.items():
            w = _trim(np.asarray(w, dtype=np.float32), sr)
            fi, fo = min(len(w) // 6, int(0.015 * sr)), min(len(w) // 4, int(0.06 * sr))
            if fi > 1:
                w[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
            if fo > 1:
                w[-fo:] *= np.cos(np.linspace(0, np.pi / 2, fo, dtype=np.float32)) ** 2      # soft natural fade-out
            self.digits[d] = (w / (_rms_active(w) or 1.0)).astype(np.float32)
        allx = np.concatenate([self.digits[d] for d in sorted(self.digits)])
        n = 2048
        frames = [allx[i:i + n] * np.hanning(n) for i in range(0, max(1, len(allx) - n), n // 2)] or [np.pad(allx, (0, n))[:n]]
        self.spec = np.sqrt(np.mean([np.abs(np.fft.rfft(f)) ** 2 for f in frames], axis=0)) + 1e-9
        self._noise_cache = None

    def noise(self, n, rng):
        if self._noise_cache is None or len(self._noise_cache) < n:
            m = max(n, int(self.sr * 6))
            g = np.random.default_rng(rng.randrange(1 << 30))
            white = np.fft.rfft(g.standard_normal(m))
            shape = np.interp(np.linspace(0, 1, len(white)), np.linspace(0, 1, len(self.spec)), self.spec)
            x = np.fft.irfft(white * shape, m).astype(np.float32)
            self._noise_cache = x / np.sqrt(np.mean(x ** 2))
        start = rng.randrange(0, len(self._noise_cache) - n + 1)
        return self._noise_cache[start:start + n].copy()


def build_trial_audio(voice, digits, snr_db, ear, rng, static_only_s=None):
    """snr_db=None -> the voice alone (no static), at the warm-up loudness. Returns (stereo int16 array [n,2], mono float32 signal for the scope, onset times of each digit in s).
    Sound plays ONLY in the tested ear; the other earphone stays silent."""
    sr = voice.sr
    sp = CFG["SPEECH_RMS"]
    if static_only_s:
        mono = voice.noise(int(sr * static_only_s), rng) * sp
        onsets = []
    else:
        parts, onsets, t = [np.zeros(int(CFG["LEAD_S"] * sr), np.float32)], [], CFG["LEAD_S"]
        for i, d in enumerate(digits):
            onsets.append(t)
            parts.append(voice.digits[d])
            t += len(voice.digits[d]) / sr
            gap = CFG["DIGIT_GAP_S"] if i < len(digits) - 1 else CFG["TAIL_S"]
            parts.append(np.zeros(int(gap * sr), np.float32))
            t += gap
        speech = np.concatenate(parts)
        if snr_db is None:
            mono = speech * sp
        else:
            mono = speech * sp + voice.noise(len(speech), rng) * sp * 10 ** (-snr_db / 20.0)
        edge = int(0.04 * sr)
        mono[:edge] *= np.linspace(0, 1, edge)
        mono[-edge:] *= np.linspace(1, 0, edge)
    peak = float(np.max(np.abs(mono))) or 1.0
    if peak > 0.97:                       # only when the static is very loud: turn everything down a little to avoid crackle
        mono = mono * (0.97 / peak)
    pcm = (mono * 32767).astype(np.int16)
    st = np.zeros((len(pcm), 2), np.int16)
    if ear == "both":
        st[:, 0] = st[:, 1] = pcm
    else:
        st[:, 0 if ear == "left" else 1] = pcm
    return st, mono, onsets


# ============================================================ simulated listener (demo + self-test)
class SimListener:
    """Gets each digit right with probability 0.11 + 0.89 * logistic(SNR - digit_srt)."""

    def __init__(self, digit_srt=-11.0, slope=0.9, rng=None):
        self.digit_srt, self.slope, self.rng = digit_srt, slope, rng or random.Random()

    def respond(self, trial):
        out = ""
        for d in trial.digits:
            p = 0.11 + 0.89 / (1 + math.exp(-(trial.snr - self.digit_srt) * self.slope))
            out += d if self.rng.random() < p else self.rng.choice([x for x in CFG["DIGITS"] if x != d])
        return out


def simulate_ear(ear, listener, rng=None):
    t = DigitsTest(ear, rng or listener.rng)
    while True:
        tr = t.next_trial()
        if tr is None:
            break
        t.answer(tr, listener.respond(tr))
    return t.results()


# ============================================================ session row + decisions
COLS = ["crew", "session", "timestamp", "data_source", "version", "room_noise", "same_headphones", "channel_check",
        "valid", "status", "srt_R", "digit_acc_R", "quality_R", "srt_L", "digit_acc_L", "quality_L", "ear_gap", "hearing_score"]


def build_row(R, L, meta):
    row = dict(meta)
    for e, x in (("R", R), ("L", L)):
        row[f"srt_{e}"], row[f"digit_acc_{e}"], row[f"quality_{e}"] = x.get("srt"), x.get("digit_acc"), x.get("quality")
        row[f"reason_{e}"] = x.get("reason", "")
        row[f"floor_{e}"] = x.get("floor", 0)
    both = R.get("srt") is not None and L.get("srt") is not None
    row["ear_gap"] = r1(abs(R["srt"] - L["srt"])) if both else None
    row["hearing_score"] = r1((R["srt"] + L["srt"]) / 2) if both else None      # mean SRT, lower = better
    ok = R.get("quality") == "ok" and L.get("quality") == "ok"
    row["valid"] = 1 if ok and meta.get("room_noise") != "loud" and meta.get("channel_check", "pass") == "pass" else 0
    return row


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def baseline(history):
    use = [h for h in history if int(h.get("valid", 0) or 0) == 1 and h.get("data_source") != "practice"][-CFG["BASELINE_MAX"]:]
    if len(use) < CFG["BASELINE_MIN"]:
        return None
    b = {"n": len(use), "n_sim": sum(1 for h in use if h.get("data_source") == "simulated")}
    for k in ("srt_R", "srt_L"):
        v = [x for x in (_num(h.get(k)) for h in use) if x is not None]
        if len(v) >= CFG["BASELINE_MIN"]:
            b[k] = float(np.median(v))
    return b


def evaluate(row, history):
    base = baseline(history)
    EN = {"R": "RIGHT", "L": "LEFT"}
    flags, notes = {"R": [], "L": []}, []
    if row.get("room_noise") == "loud":
        notes.append("you said it's loud around you: move somewhere quieter and retest")
    if row.get("channel_check") == "fail":
        notes.append("the left/right earphone check failed: headphones may be swapped")
    if row.get("same_headphones") == "no":
        notes.append("different headphones from usual: compare with care")
    for e in "RL":
        if row.get(f"quality_{e}") != "ok":
            notes.append(f"{EN[e]} ear: {row.get(f'reason_{e}') or 'unreliable'}")
        if int(row.get(f"floor_{e}") or 0):
            notes.append(f"{EN[e]} ear decoded even the noisiest codes: hearing may be even better than measured")
    worse = []
    if base:
        mode = "personal"
        for e in "RL":
            v, b = _num(row.get(f"srt_{e}")), base.get(f"srt_{e}")
            if v is not None and b is not None and v - b >= CFG["SRT_WORSE"]:
                worse.append(e)
                flags[e].append(f"needs the voice {r1(v - b)} dB louder than your normal to decode codes ({r1(b)} -> {r1(v)} dB)")
    else:
        mode = "generic"
        for e in "RL":
            v = _num(row.get(f"srt_{e}"))
            if v is not None and v > CFG["GENERIC_SRT_HIGH"]:
                worse.append(e)
                flags[e].append(f"score {r1(v)} dB is above the rough reference ({CFG['GENERIC_SRT_HIGH']} dB)")
        gap = _num(row.get("ear_gap"))
        if gap is not None and gap >= CFG["GAP_FLAG"] and not worse:
            e = "R" if _num(row["srt_R"]) > _num(row["srt_L"]) else "L"
            worse.append(e)
            flags[e].append(f"{gap} dB worse than the other ear")
    names = " and ".join(EN[e] for e in worse)
    if not int(row.get("valid", 0) or 0):
        status, head, msg = "RETEST", "Not reliable today: retest", "This check is greyed out and won't count toward your baseline."
    elif mode == "personal" and len(worse) == 1:
        status, head = "HEARING CHECK", f"Request a hearing test for the {names} ear"
        msg = (f"Only the {names} ear got worse while the other ear stayed normal. Headphones, volume or room noise would "
               "affect both ears, so this looks like a real change. Tell the flight surgeon, ask for the on-orbit hearing "
               "assessment, and wear hearing protection in loud areas (exercise, noisy modules).")
    elif mode == "personal" and len(worse) == 2:
        status, head = "CHECK", "Both ears worse than normal"
        msg = ("Something that affects both ears (volume changed, different headphones, a noisy spot) is the most likely cause. "
               "Retest with the same headphones and volume somewhere quieter. If it repeats, ask for a hearing test.")
    elif worse:
        status, head = "CHECK", "Outside the rough reference: retest tomorrow"
        msg = "Your personal baseline isn't ready yet, so this uses rough values only. If it repeats, tell the flight surgeon."
    else:
        status = "GO"
        head = "Both ears match your normal" if base else "Looks fine: your baseline is still forming"
        valid_n = sum(1 for h in history if int(h.get("valid", 0) or 0) == 1) + 1
        msg = ("Both ears decode speech through static as well as usual." if base
               else f"Valid scans so far: {min(valid_n, CFG['BASELINE_MIN'])}/{CFG['BASELINE_MIN']} before your personal baseline turns on.")
    conf = "LOW" if not int(row.get("valid", 0) or 0) else ("HIGH" if base and base["n"] >= 5 else "MEDIUM" if base else "LOW")
    why = ("unreliable session" if not int(row.get("valid", 0) or 0) else
           f"personal baseline from {base['n']} scans" + (f" ({base['n_sim']} SIMULATED)" if base["n_sim"] else "") if base
           else "no personal baseline yet")
    return {"status": status, "headline": head, "message": msg, "flags": flags, "notes": notes,
            "mode": mode, "base": base, "confidence": conf, "why": why}


def make_demo_history(crew, n=6, rng=None):
    rng = rng or random.Random()
    rows, start = [], datetime.now() - timedelta(days=n + 1)
    for i in range(1, n + 1):
        R = simulate_ear("right", SimListener(-11.0 + rng.uniform(-.5, .5), rng=rng))
        L = simulate_ear("left", SimListener(-11.3 + rng.uniform(-.5, .5), rng=rng))
        ts = (start + timedelta(days=i)).replace(hour=8, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        row = build_row(R, L, {"crew": crew, "session": i, "timestamp": ts, "data_source": "simulated", "version": CFG["VERSION"],
                               "room_noise": "normal", "same_headphones": "yes", "channel_check": "pass"})
        row["status"] = "GO" if row["valid"] else "RETEST"
        rows.append(row)
    return rows


DEMO_LEFT_DIGIT_SRT = -4.5     # simulated day-140 astronaut: LEFT ear ~6 dB worse (noise damage)


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})
    return buf.getvalue()


# ============================================================ self-test
if __name__ == "__main__":
    rng = random.Random(1)
    for d in (-11.0, -6.0, -2.0):
        v = [simulate_ear("right", SimListener(d, rng=rng))["srt"] for _ in range(200)]
        print(f"listener digit-SRT {d:+.1f} dB -> measured SRT mean {np.mean(v):+.2f}, sd {np.std(v):.2f}")
    print("random guesser:", simulate_ear("right", SimListener(40, rng=rng)))
    h = make_demo_history("A", rng=rng)
    R = simulate_ear("right", SimListener(-11, rng=rng))
    L = simulate_ear("left", SimListener(DEMO_LEFT_DIGIT_SRT, rng=rng))
    ev = evaluate(build_row(R, L, {"crew": "A", "session": 7, "room_noise": "normal", "channel_check": "pass"}), h)
    print(ev["status"], "|", ev["headline"], "|", ev["flags"])
    # audio sanity check with fake "digits"
    sr = 22050
    waves = {d: np.sin(2 * np.pi * (200 + 40 * int(d)) * np.arange(int(sr * .4)) / sr) for d in "0123456789"}
    v = Voice(waves, sr)
    st, mono, on = build_trial_audio(v, "123", -6, "left", rng)
    print("audio", st.shape, "right channel silent:", int(np.abs(st[:, 1]).max()) == 0, "onsets", [round(x, 2) for x in on])
