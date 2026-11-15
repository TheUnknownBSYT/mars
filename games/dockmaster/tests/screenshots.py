"""Real DOCKMASTER screenshots from the game's own drawing code.   python tests/screenshots.py OUT_DIR"""
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pil_pygame  # noqa: E402

pg = pil_pygame.install()
import fake_pygame  # noqa: E402
import config as C  # noqa: E402

tmp = Path(tempfile.mkdtemp())
C.DATA_DIR, C.SESSIONS_CSV, C.EVENTS_CSV = tmp, tmp / "s.csv", tmp / "e.csv"
import main  # noqa: E402
from core import generators as G, logger  # noqa: E402
from game import rounds, screens  # noqa: E402
from game.base import Session  # noqa: E402
from test_core import fake_events  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
out.mkdir(parents=True, exist_ok=True)
app = main.App("AST-01")
logger.make_demo_history("AST-01", seed=4)
NOW = time.perf_counter()


def shot(sc, name, now=NOW):
    app.screen.fill((0, 0, 0))
    sc.draw(app.screen, now)
    app.screen.img.convert("RGB").save(out / f"{name}.png")
    print("saved", name)


ci = screens.CheckinScene(app)
ci.refresh()
ci.sleep, ci.fatigue, ci.stress, ci.mood, ci.sel = 6.5, 3, 2, 4, 2
shot(ci, "01_checkin")
app.session = s = Session("AST-01", {"sleep_hours": 6.5, "fatigue": 3, "stress": 2, "mood": 4, "input_device": "mouse"})
shot(screens.BriefingScene(app, 1), "02_briefing")

# Task 1
t1 = rounds.PortTask(app, G.port_rounds(random.Random(3)))
t1.started = True
t1.begin(NOW - 0.6)
shot(t1, "03_ports_memorise")
t1.set("recall", NOW - 1)
t1.last_t = NOW
t1.used = {0: 1, 1: 2}
t1.expected = 3
fake_pygame.MOUSE["pos"] = tuple(int(v) for v in t1.rnd["ports"][2])
app.mouse = fake_pygame.MOUSE["pos"]
shot(t1, "04_ports_recall")
t1.used = {0: 1, 1: 2, 2: 3, 4: 4, 3: 5}
t1.ok = False
t1.set("feedback", NOW)
shot(t1, "05_ports_feedback")

# Task 2
t2 = rounds.TrackTask(app, G.track_rounds(random.Random(5)))
t2.started = True
t2.begin(NOW - 0.3)
shot(t2, "06_track_blink")
t2.set("move", NOW - 3.0)
t2.pos = t2.frames[180]
shot(t2, "07_track_moving")
t2.pos = t2.frames[-1]
t2.picks = [t2.rnd["tagged"][0], [j for j in range(6) if j not in t2.rnd["tagged"]][0]]
t2.ok = 1
t2.set("feedback", NOW)
shot(t2, "08_track_feedback")

# Task 3
t3 = rounds.BeamTask(app, G.beam_rounds(random.Random(8)))
t3.started = True
t3.begin(NOW)
ft = t3.rnd["flashes"][1][0]
t3.set("track", NOW - ft - 0.1)
tp = G.beam_position(t3.rnd, ft + 0.1)
fake_pygame.MOUSE["pos"] = (int(tp[0] + 12), int(tp[1] - 8))
app.mouse = fake_pygame.MOUSE["pos"]
t3.on_time, t3.t_total = 0.82 * (ft + 0.1), ft + 0.1
shot(t3, "09_beam_tracking")
t3.state = "track"
t3.step(NOW + C.T3_DURATION_S, 0.01)
t3.ts = NOW - 2
shot(t3, "10_beam_answer")

# Debrief
s.events = dict(zip((1, 2, 3), fake_events(random.Random(3))))
shot(screens.DebriefScene(app), "11_debrief_go")
app.session = s2 = Session("AST-01", {"sleep_hours": 4.5, "fatigue": 6, "stress": 3, "mood": 2, "input_device": "mouse"})
s2.events = dict(zip((1, 2, 3), fake_events(random.Random(4), slow=1.5, count_bad=True)))
shot(screens.DebriefScene(app), "12_debrief_nogo")
