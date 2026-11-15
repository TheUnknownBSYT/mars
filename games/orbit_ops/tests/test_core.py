"""
Tests for the core logic. Run from the orbit_ops folder:
    python -m pytest tests        (or)    python tests/test_core.py
No pygame needed.
"""
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C  # noqa: E402

_tmp = Path(tempfile.mkdtemp())
C.DATA_DIR = _tmp
C.SESSIONS_CSV = _tmp / "sessions.csv"
C.TRIALS_CSV = _tmp / "trials.csv"
C.PROGRESS_JSON = _tmp / "progress.json"

from core import schedule, scoring, readiness, logger, progression  # noqa: E402


def fake_player(rng, r1_rt=280, go_extra=120, rep=650, cost=160, slow=0, fa_rate=0.05, err=0.03):
    """Simulate a player answering all three rounds."""
    r1 = []
    for t in schedule.build_round1(rng):
        rt = rng.gauss(r1_rt + slow, 35)
        r1.append({**t, "response": "hit", "correct": 1, "rt_ms": rt, "lapse": int(rt >= C.R1_LAPSE_MS)})
    r2 = []
    for t in schedule.build_round2(rng):
        if t["condition"] == "go":
            r2.append({**t, "response": "hit", "correct": 1, "rt_ms": rng.gauss(r1_rt + go_extra + slow, 40)})
        elif rng.random() < fa_rate:
            r2.append({**t, "response": "false_alarm", "correct": 0, "rt_ms": 350})
        else:
            r2.append({**t, "response": "correct_rejection", "correct": 1, "rt_ms": None})
    r3 = []
    for t in schedule.build_round3(rng):
        base = rep + (cost if t["condition"] == "switch" else 0) + slow
        ok = rng.random() > err
        r3.append({**t, "response": "correct" if ok else "old_rule", "correct": int(ok),
                   "rt_ms": rng.gauss(base, 50)})
    return r1, r2, r3


def test_schedules():
    rng = random.Random(1)
    r1 = schedule.build_round1(rng)
    assert len(r1) == C.R1_TRIALS
    assert all(C.R1_ISI_S[0] <= t["isi_s"] <= C.R1_ISI_S[1] for t in r1)
    r2 = schedule.build_round2(rng)
    assert sum(t["condition"] == "go" for t in r2) == C.R2_GO_TRIALS
    r3 = schedule.build_round3(rng)
    assert len(r3) == C.R3_TRIALS
    assert sum(t["is_switch"] for t in r3) >= 3
    for t in r3:
        assert t["correct_key"] == schedule.correct_key_r3(t["rule"], t["shape"], t["color"])
        if not t["congruent"]:
            assert C.R3_SHAPE_MAP[t["shape"]] != C.R3_COLOR_MAP[t["color"]]


def test_scoring_values():
    r1 = [{"round": 1, "condition": "alarm", "response": "hit", "correct": 1, "rt_ms": v}
          for v in [250, 260, 270, 280, 290, 300, 400, 260, 270]]
    r1.append({"round": 1, "condition": "alarm", "response": "miss", "correct": 0, "rt_ms": None})
    r1.append({"round": 1, "condition": "alarm", "response": "false_start", "correct": 0, "rt_ms": 50})
    s = scoring.score_round1(r1)
    assert s["r1_median_ms"] == 270
    assert s["r1_lapses"] == 2          # 400 ms + 1 miss
    assert s["r1_false_starts"] == 1
    assert s["r1_valid"] == 9


def test_session_and_readiness_flow():
    rng = random.Random(7)
    crew = "TEST-1"
    # 8 normal sessions
    for i in range(1, 9):
        sc = scoring.score_session(*fake_player(rng))
        ev = readiness.evaluate(sc, {"sleep_hours": 7.5, "fatigue": 2, "stress": 2},
                                logger.load_history(crew), i)
        row = {**sc, "astronaut": crew, "session_index": i, "data_source": "prototype_gameplay",
               "invalid": int(ev["invalid"]), "status": ev["status"]}
        logger.save_session(row)
        if i <= 3:
            assert ev["mode"] == "generic"
    hist = logger.load_history(crew)
    assert len(hist) == 8
    base = readiness.build_baseline(hist)
    assert base and base["n"] == 5

    # normal day -> GO with HIGH confidence
    sc = scoring.score_session(*fake_player(rng))
    ev = readiness.evaluate(sc, {"sleep_hours": 7.5, "fatigue": 2, "stress": 2}, hist, 9)
    assert ev["status"] == "GO", ev
    assert ev["confidence"] == "HIGH"

    # slow + short sleep -> NO-GO
    sc = scoring.score_session(*fake_player(rng, slow=120))
    ev = readiness.evaluate(sc, {"sleep_hours": 4.5, "fatigue": 6, "stress": 3}, hist, 9)
    assert ev["status"] == "NO-GO", ev
    assert ev["components"]["alertness"]["status"] == "slower"

    # only adaptation worse (bigger switch cost) + good sleep -> CAUTION, adaptation flagged
    sc = scoring.score_session(*fake_player(rng, cost=480))
    ev = readiness.evaluate(sc, {"sleep_hours": 8, "fatigue": 2, "stress": 2}, hist, 9)
    assert ev["status"] == "CAUTION", ev
    assert ev["components"]["adaptation"]["status"] == "slower"
    assert ev["components"]["alertness"]["status"] == "normal"

    # too many false starts -> RETEST
    sc = scoring.score_session(*fake_player(rng))
    sc["r1_false_starts"] = 9
    ev = readiness.evaluate(sc, {"sleep_hours": 8, "fatigue": 2, "stress": 2}, hist, 9)
    assert ev["status"] == "RETEST"


def test_demo_and_progression():
    crew = "DEMO-1"
    logger.make_demo_history(crew, seed=3)
    hist = logger.load_history(crew)
    assert len(hist) == 8 and all(h["data_source"] == "simulated" for h in hist)
    base = readiness.build_baseline(hist)
    assert base["n_simulated"] == 5
    rng = random.Random(2)
    sc = scoring.score_session(*fake_player(rng))
    p = progression.update(crew, sc, hist)
    assert p["sessions_done"] == 9 and p["rank"] == "Pilot"
    assert any(b[0] == "First Docking" for b in p["new_badges"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
