"""DOCKMASTER core tests (no pygame).   python tests/test_core.py"""
import math
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402

_t = Path(tempfile.mkdtemp())
C.DATA_DIR, C.SESSIONS_CSV, C.EVENTS_CSV = _t, _t / "s.csv", _t / "e.csv"
from core import generators as G, logger, readiness, scoring  # noqa: E402


def fake_events(rng, slow=1.0, mem_bad=False, count_bad=False):
    e1 = []
    for r in range(C.T1_ROUNDS):
        for k in range(C.T1_PORTS):
            ok = not (mem_bad and k in (2, 3))
            e1.append({"kind": "click", "round": r + 1, "expected": k + 1, "clicked": k + 1 if ok else 5 - k, "correct": int(ok),
                       "dt_ms": 560 * slow + rng.uniform(-40, 40), "err_px": 7 * slow + rng.uniform(-1, 1), "first": int(k == 0)})
        e1.append({"kind": "round", "round": r + 1, "perfect": int(not mem_bad), "timeout": 0, "first_click_ms": 900 * slow})
    e2 = []
    for r in range(C.T2_ROUNDS):
        nc = 0 if mem_bad else 2
        for k in range(2):
            e2.append({"kind": "pick", "round": r + 1, "correct": int(k < nc), "time_ms": 1500 * slow, "err_px": 8})
        e2.append({"kind": "round", "round": r + 1, "n_correct": nc, "n_targets": 2, "timeout": 0})
    e3 = [{"kind": "beam", "round": r + 1, "track_err_px": 18 * slow, "on_target_pct": 78 / slow, "greens": 4,
           "answer": 2 if count_bad else 4, "count_err": 2 if count_bad else 0, "answer_ms": 2200} for r in range(C.T3_ROUNDS)]
    return e1, e2, e3


def test_generators():
    rng = random.Random(1)
    for rnd in G.port_rounds(rng):
        p = rnd["ports"]
        assert len(p) == C.T1_PORTS
        assert all(math.hypot(a[0] - b[0], a[1] - b[1]) >= C.T1_MIN_GAP for i, a in enumerate(p) for b in p[i + 1:])
    tr = G.track_rounds(rng)[0]
    a, b = G.simulate_track(tr, 3.0), G.simulate_track(tr, 3.0)
    assert a == b                                               # deterministic
    x, y, w, h = C.ARENA
    assert all(x <= px <= x + w and y <= py <= y + h for px, py in G.simulate_track(tr, C.T2_MOVE_S))
    for br in G.beam_rounds(rng, 20):
        times = [f[0] for f in br["flashes"]]
        assert all(t2 - t1 >= C.T3_FLASH_GAP_S - 1e-9 for t1, t2 in zip(times, times[1:]))
        assert br["greens"] == sum(1 for f in br["flashes"] if f[1] == "green")
        px, py = G.beam_position(br, 7.3)
        assert x < px < x + w and y < py < y + h


def test_scoring_and_readiness():
    rng = random.Random(2)
    sc = scoring.score_session(*fake_events(rng))
    assert sc["t1_order_acc"] == 1.0 and sc["t2_accuracy"] == 1.0 and sc["t3_count_err"] == 0
    logger.make_demo_history("D", seed=3)
    hist = logger.load_history("D")
    ok = readiness.evaluate(sc, {"sleep_hours": 7.5, "fatigue": 2, "stress": 2}, hist, 9)
    assert ok["status"] == "GO" and ok["confidence"] == "HIGH", ok["components"]
    slow = readiness.evaluate(scoring.score_session(*fake_events(rng, slow=1.6)), {"sleep_hours": 4.5, "fatigue": 6}, hist, 9)
    assert slow["status"] == "NO-GO" and slow["components"]["hand_eye"]["status"] == "slower"
    mem = readiness.evaluate(scoring.score_session(*fake_events(rng, mem_bad=True)), {"sleep_hours": 8, "fatigue": 2}, hist, 9)
    assert mem["status"] == "CAUTION" and mem["components"]["memory"]["status"] == "slower" and mem["components"]["hand_eye"]["status"] == "normal"
    att = readiness.evaluate(scoring.score_session(*fake_events(rng, count_bad=True)), {"sleep_hours": 8, "fatigue": 2}, hist, 9)
    assert att["components"]["attention"]["status"] == "slower"
    gen = readiness.evaluate(sc, {"sleep_hours": 8, "fatigue": 2}, [], 1)
    assert gen["confidence"] == "LOW" and gen["status"] == "GO"


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("PASS", n)
