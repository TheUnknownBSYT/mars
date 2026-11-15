"""
Headless end-to-end test: a bot plays a full DOCKMASTER shift (plus one practice
round) with shortened timings, then checks the saved data.   python tests/smoke_test.py
"""
import csv
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_pygame  # noqa: E402

pg = fake_pygame.install()
import config as C  # noqa: E402

tmp = Path(tempfile.mkdtemp())
C.DATA_DIR, C.SESSIONS_CSV, C.EVENTS_CSV = tmp, tmp / "sessions.csv", tmp / "events.csv"
C.T1_SHOW_S, C.T1_FEEDBACK_S = 0.2, 0.1
C.T2_BLINK_S, C.T2_MOVE_S, C.T2_FEEDBACK_S = 0.2, 1.0, 0.1
C.T3_DURATION_S = 6.0
C.T3_FLASH_GAP_S = 0.5

import main  # noqa: E402
from core import generators as G  # noqa: E402
from game import rounds, screens  # noqa: E402

M = fake_pygame.MOUSE
rng = random.Random(1)


def key(k, u=""):
    return pg.event.Event(pg.KEYDOWN, key=k, unicode=u)


def click(p):
    return pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(int(p[0]), int(p[1])))


class Bot:
    def __init__(self, app):
        self.app, self.q, self.log, self.last, self.t = app, [], [], None, 0
        self.demo = self.prac = False
        self.next_click = 0

    def events(self):
        s, now = self.app.scene, time.perf_counter()
        if s is not self.last:
            self.last, self.t = s, now
            self.log.append(type(s).__name__ + ("(practice)" if getattr(s, "practice", False) else ""))
        if self.q:
            return [self.q.pop(0)]
        if isinstance(s, screens.CheckinScene):
            if not self.demo:
                self.demo = True
                return [key(pg.K_F2)]
            self.q = [key(pg.K_LEFT), key(pg.K_DOWN), key(9001, "3"), key(pg.K_DOWN), key(9002, "2"), key(pg.K_DOWN), key(9003, "4"), key(pg.K_RETURN)]
            return []
        if isinstance(s, screens.BriefingScene):
            if now - self.t < 0.05:
                return []
            if s.rnd == 1 and not self.prac:
                self.prac = True
                return [key(pg.K_p)]
            return [key(pg.K_SPACE)]
        if now < self.next_click:
            return []
        if isinstance(s, rounds.PortTask) and s.state == "recall":
            k = s.expected - 1
            if rng.random() < 0.08:                      # occasional wrong port
                k = next(j for j in range(C.T1_PORTS) if j not in s.used)
            p = s.rnd["ports"][k]
            self.next_click = now + 0.12
            return [click((p[0] + rng.gauss(0, 4), p[1] + rng.gauss(0, 4)))]
        if isinstance(s, rounds.TrackTask) and s.state == "answer":
            todo = [j for j in s.rnd["tagged"] if j not in s.picks]
            j = todo[0] if rng.random() > 0.1 else next(x for x in range(C.T2_SATELLITES) if x not in s.picks)
            self.next_click = now + 0.15
            return [click(s.pos[j])]
        if isinstance(s, rounds.BeamTask):
            if s.state == "track":
                tp = G.beam_position(s.rnd, s.age(now))
                M["pos"] = (int(tp[0] + rng.gauss(0, 8)), int(tp[1] + rng.gauss(0, 8)))
            if s.state == "answer" and s.age(now) > 0.2:
                ans = s.rnd["greens"]
                r = next(r for r, k in s.btns if k == ans)
                return [click(r.center)]
            return []
        if isinstance(s, screens.DebriefScene) and now - self.t > 0.05:
            return [key(pg.K_t), key(pg.K_t), key(pg.K_ESCAPE)]
        return []


if __name__ == "__main__":
    app = main.App("SMK-1")
    bot = Bot(app)
    pg.event.get = lambda: bot.events()
    t0 = time.perf_counter()
    app.run()
    flow = [n for i, n in enumerate(bot.log) if i == 0 or n != bot.log[i - 1]]
    print("Flow:", " > ".join(flow))
    rows = list(csv.DictReader(open(C.SESSIONS_CSV)))
    ev = list(csv.DictReader(open(C.EVENTS_CSV)))
    real = [r for r in rows if r["data_source"] == "prototype_gameplay"]
    assert len(real) == 1 and sum(r["data_source"] == "simulated" for r in rows) == 8
    r = real[0]
    for k in ["session_index", "sleep_hours", "fatigue", "t1_order_acc", "t1_perfect_rounds", "t1_click_time_ms", "t1_click_err_px",
              "t2_correct", "t2_accuracy", "t2_select_time_ms", "t3_track_err_px", "t3_on_target_pct", "t3_count_err",
              "hand_eye", "memory", "attention", "status", "confidence", "baseline_mode"]:
        print(f"  {k:20s} {r[k]}")
    print("events:", len(ev), sorted({e['kind'] for e in ev}))
    assert r["session_index"] == "9" and int(r["t1_rounds"]) == C.T1_ROUNDS and int(r["t2_rounds"]) == C.T2_ROUNDS and int(r["t3_rounds"]) == C.T3_ROUNDS
    assert float(r["t3_on_target_pct"]) > 50 and r["t3_count_err"] == "0"
    print("SMOKE TEST PASSED in %.0f s" % (time.perf_counter() - t0))
