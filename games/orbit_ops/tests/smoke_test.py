"""
Headless end-to-end smoke test: a bot plays two full sessions (with practice
rounds, a demo-history load, pause/resume) on a fake pygame, with timings
shortened. Checks that data is saved correctly.

    python tests/smoke_test.py
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

# ---- shorten everything BEFORE the game modules are imported
tmp = Path(tempfile.mkdtemp())
C.DATA_DIR, C.SESSIONS_CSV, C.TRIALS_CSV, C.PROGRESS_JSON = tmp, tmp / "sessions.csv", tmp / "trials.csv", tmp / "progress.json"
C.R1_TRIALS, C.R1_ISI_S, C.R1_TIMEOUT_S, C.R1_FEEDBACK_S = 20, (0.02, 0.05), 0.6, 0.05
C.R2_TRIALS, C.R2_GO_TRIALS, C.R2_ISI_S, C.R2_WINDOW_S, C.R2_FEEDBACK_S = 14, 10, (0.02, 0.04), 0.4, 0.05
C.R3_TRIALS, C.R3_ISI_S, C.R3_WINDOW_S, C.R3_NEW_ORDERS_S, C.R3_FEEDBACK_S = 16, (0.02, 0.04), 0.7, 0.05, 0.05
C.BREATHER_S = 0.3
C.PRACTICE_TRIALS = {1: 2, 2: 3, 3: 3}

import main  # noqa: E402
from game import rounds, screens  # noqa: E402

screens.DockingScene.DUR = 0.2

rng = random.Random(5)
K = pg


def key(k, uni=""):
    return pg.event.Event(pg.KEYDOWN, key=k, unicode=uni)


class Bot:
    def __init__(self, app):
        self.app = app
        self.sessions_seen = 0
        self.debriefs = 0
        self.pending = []
        self.briefs_practiced = set()
        self.did_early = False
        self.did_pause = False
        self.last_scene = None
        self.scene_t = 0
        self.log = []

    def events(self):
        app, s = self.app, self.app.scene
        now = time.perf_counter()
        if s is not self.last_scene:
            self.last_scene, self.scene_t = s, now
            self.log.append(type(s).__name__)
        if self.pending:
            return [self.pending.pop(0)]
        name = type(s).__name__
        if name == "CheckinScene":
            if self.debriefs == 0 and not getattr(self, "demo_loaded", False):
                self.demo_loaded = True
                return [key(K.K_F2)]
            self.pending = [key(K.K_LEFT), key(K.K_DOWN), key(K.K_4, "4") if hasattr(K, "K_4") else key(9999, "4"),
                            key(K.K_DOWN), key(9998, "2"), key(K.K_DOWN), key(9997, "3"),
                            key(K.K_DOWN), key(K.K_RIGHT), key(K.K_LEFT), key(K.K_RETURN)]
            # first key moves sleep 7.0 -> 6.5 (sel starts on sleep)
            return []
        if name == "BriefingScene":
            tag = (self.debriefs, s.rnd)
            if self.debriefs == 0 and tag not in self.briefs_practiced:
                self.briefs_practiced.add(tag)
                return [key(K.K_p)]
            return [key(K.K_SPACE)] if now - self.scene_t > 0.05 else []
        if isinstance(s, rounds.RoundScene):
            if not s.practice and not self.did_pause and s.number == 2 and s.i == 3 and s.state == "isi":
                self.did_pause = True
                return [key(K.K_ESCAPE), key(K.K_RETURN)]
            if s.number == 1 and not s.practice and not self.did_early and s.state == "isi":
                self.did_early = True
                return [key(K.K_SPACE)]
            if s.state == "stim" and s.onset is not None and now - s.onset > 0.13 + rng.random() * 0.05:
                t = s.trial
                if s.number == 1:
                    return [key(K.K_SPACE)]
                if s.number == 2:
                    return [key(K.K_SPACE)] if t["stimulus"] == "debris" or rng.random() < 0.15 else []
                if s.number == 3:
                    right = t["correct_key"] if rng.random() > 0.1 else ("left" if t["correct_key"] == "right" else "right")
                    return [key(K.K_f if right == "left" else K.K_j)]
            return []
        if name == "BreatherScene":
            return []
        if name == "MoodScene":
            return [key(9996, "4"), key(K.K_RETURN)]
        if name == "DockingScene":
            return []
        if name == "DebriefScene":
            if now - self.scene_t < 0.05:
                return []
            self.debriefs += 1
            if self.debriefs == 1:
                return [key(K.K_t), key(K.K_t), key(K.K_RETURN)]
            return [key(K.K_ESCAPE)]
        return []


def run():
    app = main.App("SMOKE-1")
    bot = Bot(app)
    pg.event.get = lambda: bot.events()
    t0 = time.perf_counter()
    # safety stop
    orig_update = app.scene.__class__.update

    def guard():
        if time.perf_counter() - t0 > 240:
            raise SystemExit("smoke test timed out in scene " + type(app.scene).__name__)

    old_go = app.go

    def go(scene):
        guard()
        old_go(scene)

    app.go = go
    app.run()
    return bot


if __name__ == "__main__":
    bot = run()
    flow = [n for i, n in enumerate(bot.log) if i == 0 or n != bot.log[i - 1]]
    print("Scene flow:", " > ".join(flow))
    with open(C.SESSIONS_CSV, newline="") as f:
        sessions = list(csv.DictReader(f))
    with open(C.TRIALS_CSV, newline="") as f:
        trials = list(csv.DictReader(f))
    print(f"sessions.csv rows: {len(sessions)}   trials.csv rows: {len(trials)}")
    real = [r for r in sessions if r["data_source"] == "prototype_gameplay"]
    for r in real:
        print({k: r[k] for k in ("astronaut", "session_index", "sleep_hours", "fatigue", "stress", "mood_pre", "mood_post",
                                 "reaction_ms", "r1_lapses", "r1_false_starts", "r2_false_alarms", "decision_time_ms",
                                 "switch_cost_ms", "r3_accuracy", "status", "confidence", "baseline_mode")})
    assert len(real) == 2, "expected 2 real sessions saved"
    assert sum(1 for r in sessions if r["data_source"] == "simulated") == 8
    assert real[0]["sleep_hours"] == "6.5" and real[0]["fatigue"] == "4" and real[0]["mood_post"] == "4"
    assert int(real[0]["r1_false_starts"]) >= 1, "early press should be logged"
    assert real[0]["session_index"] == "9", "demo history (8) + new session = 9"
    assert real[0]["baseline_mode"] == "personal_n5_sim5", real[0]["baseline_mode"]
    assert real[1]["session_index"] == "10" and real[1]["baseline_mode"] == "personal_n6_sim5"
    r1 = [t for t in trials if t["round"] == "1" and t["session_index"] == "9"]
    assert sum(t["response"] in ("hit", "miss") for t in r1) + sum(t["response"] == "false_start" and t["rt_ms"] != "" for t in r1) == C.R1_TRIALS
    assert len([t for t in trials if t["round"] == "3" and t["session_index"] == "9"]) >= C.R3_TRIALS
    assert all(t["data_source"] == "prototype_gameplay" for t in trials)
    print("SMOKE TEST PASSED")
