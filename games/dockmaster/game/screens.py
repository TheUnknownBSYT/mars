"""Check-in, briefings and debrief for DOCKMASTER."""
import pygame

import config as C
from core import logger, readiness, scoring
from game import gfx
from game.base import CONSOLE, Scene, Session, footer, header
from game.rounds import TASKS

FATIGUE = ["Fully alert", "Very lively", "OK, somewhat fresh", "A little tired", "Moderately tired", "Extremely tired", "Completely exhausted"]
STRESS = ["Very low", "Low", "Moderate", "High", "Very high"]
MOOD = ["Very low", "Low", "Neutral", "Good", "Very good"]
DEVICES = ["mouse", "trackpad", "touchscreen"]


def advance(app):
    s = app.session
    s.step += 1
    step = Session.STEPS[s.step]
    nxt = lambda: advance(app)
    if step.startswith("brief"):
        app.go(BriefingScene(app, int(step[-1])))
    elif step == "ports":
        app.go(TASKS[1](app, s.ports, on_done=nxt))
    elif step == "track":
        app.go(TASKS[2](app, s.track, on_done=nxt))
    elif step == "beam":
        app.go(TASKS[3](app, s.beam, on_done=nxt))
    else:
        app.go(DebriefScene(app))


# =====================================================================
class CheckinScene(Scene):
    FIELDS = ["crew", "sleep", "fatigue", "stress", "mood", "device", "mode"]

    def __init__(self, app):
        super().__init__(app)
        self.sel = 1
        self.crew = app.crew
        self.sleep, self.fatigue, self.stress, self.mood = 7.0, None, None, None
        self.device = 0
        self.practice = False
        self.msg, self.msg_col = "", gfx.AMBER
        self.confirm = False
        self.refresh()

    def refresh(self):
        self.crew = "".join(ch for ch in self.crew.upper() if ch.isalnum() or ch in "-_")[:12] or "AST-01"
        self.app.crew = self.crew
        self.history = logger.load_history(self.crew)
        self.base = readiness.build_baseline(self.history)

    def handle(self, e, now):
        if e.type != pygame.KEYDOWN:
            return
        f, k = self.FIELDS[self.sel], e.key
        if k == pygame.K_ESCAPE:
            self.app.running = False
        elif k == pygame.K_UP:
            self.sel = (self.sel - 1) % len(self.FIELDS)
        elif k in (pygame.K_DOWN, pygame.K_TAB):
            self.sel = (self.sel + 1) % len(self.FIELDS)
        elif k == pygame.K_F2:
            logger.make_demo_history(self.crew)
            self.refresh()
            self.msg, self.msg_col = f"Loaded 8 SIMULATED shifts for {self.crew} (data_source=simulated).", gfx.ACCENT
        elif k == pygame.K_F3:
            if self.confirm:
                logger.clear(self.crew)
                self.refresh()
                self.msg, self.msg_col, self.confirm = f"History cleared for {self.crew}.", gfx.ACCENT, False
            else:
                self.confirm = True
                self.msg, self.msg_col = f"Press F3 again to delete all shifts for {self.crew}.", gfx.RED
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.start()
        elif f == "crew":
            if k == pygame.K_BACKSPACE:
                self.crew = self.crew[:-1]
            elif e.unicode and (e.unicode.isalnum() or e.unicode in "-_") and len(self.crew) < 12:
                self.crew += e.unicode.upper()
            if self.crew:
                self.refresh()
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            d = 1 if k == pygame.K_RIGHT else -1
            if f == "sleep":
                self.sleep = min(12.0, max(0.0, self.sleep + 0.5 * d))
            elif f in ("fatigue", "stress", "mood"):
                hi = 7 if f == "fatigue" else 5
                cur = getattr(self, f)
                setattr(self, f, min(hi, max(1, (cur + d) if cur else (3 if f != "mood" else 4))))
            elif f == "device":
                self.device = (self.device + d) % len(DEVICES)
            elif f == "mode":
                self.practice = not self.practice
        elif e.unicode and e.unicode.isdigit() and f in ("fatigue", "stress", "mood"):
            v, hi = int(e.unicode), (7 if f == "fatigue" else 5)
            if 1 <= v <= hi:
                setattr(self, f, v)

    def start(self):
        miss = [n for n in ("fatigue", "stress", "mood") if getattr(self, n) is None]
        if miss:
            self.msg, self.msg_col = "Please rate " + ", ".join(miss) + " (LEFT/RIGHT or number keys).", gfx.AMBER
            return
        self.app.session = Session(self.crew, {"sleep_hours": self.sleep, "fatigue": self.fatigue, "stress": self.stress,
                                               "mood": self.mood, "input_device": DEVICES[self.device]}, self.practice)
        advance(self.app)

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        header(surf, self.app, "PRE-SHIFT CHECK-IN", "3-minute hand-eye · memory · attention check")
        gfx.text(surf, "Daily operator readiness", (50, 80), 34, gfx.TEXT, bold=True)
        gfx.text(surf, "Three 1-minute tasks with one simple rule each. Use the same mouse every day.", (50, 122), 18, gfx.MUTED)
        box = pygame.Rect(40, 160, 640, 480)
        gfx.panel(surf, box, CONSOLE)
        val = lambda v, L: f"{v} · {L[v - 1]}" if v else "-- rate --"
        rows = [("CREW ID", self.crew + ("_" if self.sel == 0 and int(now * 2) % 2 == 0 else "")),
                ("SLEEP LAST NIGHT", f"{self.sleep:.1f} h"),
                ("FATIGUE (1-7)", val(self.fatigue, FATIGUE)), ("STRESS (1-5)", val(self.stress, STRESS)),
                ("MOOD (1-5)", val(self.mood, MOOD)), ("INPUT DEVICE (keep the same every day)", DEVICES[self.device]),
                ("MODE", "PRACTICE (not saved)" if self.practice else "SHIFT (saved)")]
        y = 176
        for i, (lab, v) in enumerate(rows):
            r = pygame.Rect(56, y, 608, 60)
            if i == self.sel:
                gfx.panel(surf, r, gfx.PANEL2, gfx.ACCENT, 8, 2)
                if i > 0:
                    gfx.text(surf, "<  >", (650, y + 30), 18, gfx.ACCENT, bold=True, mono=True, anchor="topright")
            gfx.text(surf, lab, (72, y + 8), 13, gfx.MUTED, bold=True, mono=True)
            gfx.text(surf, v, (72, y + 28), 22, gfx.TEXT if "rate" not in v else gfx.DIM, bold=True)
            y += 66
        rb = pygame.Rect(710, 160, 530, 230)
        n = len(self.history)
        nsim = sum(1 for h in self.history if h.get("data_source") == "simulated")
        lines = [f"{n} saved shifts" + (f" ({nsim} simulated)" if nsim else "")]
        if n < C.FAMILIARISATION_SESSIONS:
            lines.append(f"Familiarisation {n}/{C.FAMILIARISATION_SESSIONS}: learning the tasks, not used for baseline")
        else:
            lines.append(f"Personal baseline ACTIVE ({self.base['n']} shifts)" if self.base else "Personal baseline forming")
        if n:
            lines.append(f"Last status: {self.history[-1].get('status')}  ({str(self.history[-1].get('timestamp'))[:10]})")
        gfx.panel(surf, rb, CONSOLE)
        gfx.text(surf, "OPERATOR RECORD", (730, 176), 13, gfx.MUTED, bold=True, mono=True)
        yy = 206
        for ln in lines:
            yy = gfx.text_block(surf, ln, (730, yy), 490, 18, gfx.TEXT) + 8
        mb = pygame.Rect(710, 405, 530, 235)
        gfx.panel(surf, mb, CONSOLE)
        gfx.text(surf, "TODAY'S SHIFT", (730, 421), 13, gfx.MUTED, bold=True, mono=True)
        for j, (a, b) in enumerate([("1  PORT SEQUENCE", "click ports in order 1-5 from memory"), ("2  TRACK THE SATELLITE", "follow the blinking satellites, click them"),
                                    ("3  STEADY BEAM", "keep the laser on target, count green flashes")]):
            gfx.text(surf, a, (730, 456 + j * 50), 20, gfx.TEXT, bold=True, mono=True)
            gfx.text(surf, b, (730, 480 + j * 50), 15, gfx.MUTED)
        if self.msg:
            gfx.text(surf, self.msg, (50, 650), 16, self.msg_col)
        footer(surf, "UP/DOWN select · LEFT/RIGHT or digits set · ENTER start · F2 demo history · F3 clear · F11 fullscreen · ESC quit")


# =====================================================================
class BriefingScene(Scene):
    INFO = {
        1: ("PORT SEQUENCE", "memory · hand-eye", "Click the docking ports in order: 1 → 2 → 3 → 4 → 5",
            ["5 numbered docking ports appear for 1.5 seconds.", "The numbers disappear.", "Click the ports in the right order from memory, as fast and accurately as you can."]),
        2: ("TRACK THE SATELLITE", "memory · eye tracking · hand-eye", "Follow the satellites that blink. Click them when they stop.",
            ["6 identical satellites. 2 of them blink amber.", "They all move around for 6 seconds and cross each other. Follow the 2 with your eyes.", "When they stop, click the 2 that blinked."]),
        3: ("STEADY BEAM", "hand-eye · attention", "Keep the laser on the satellite AND count the GREEN flashes.",
            ["A satellite drifts smoothly around the screen. Keep the laser (your mouse) on it.", "Lights flash at the edges: count only the GREEN ones, ignore red.", "After 25 seconds, click how many green flashes you saw."]),
    }

    def __init__(self, app, rnd):
        super().__init__(app)
        self.rnd = rnd

    def handle(self, e, now):
        if e.type != pygame.KEYDOWN:
            return
        s = self.app.session
        if e.key == pygame.K_SPACE:
            advance(self.app)
        elif e.key == pygame.K_p:
            import random
            from core import generators as G
            s.practiced.add(self.rnd)
            rng = random.Random()
            back = lambda: self.app.go(BriefingScene(self.app, self.rnd))
            gen = {1: G.port_rounds, 2: G.track_rounds, 3: G.beam_rounds}[self.rnd]
            self.app.go(TASKS[self.rnd](self.app, gen(rng, 1), practice=True, on_done=back))
        elif e.key == pygame.K_ESCAPE:
            self.app.session = None
            self.app.go(CheckinScene(self.app))

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        title, skills, rule, lines = self.INFO[self.rnd]
        header(surf, self.app, "SHIFT BRIEFING", f"TASK {self.rnd} OF 3 · ~1 minute")
        gfx.text(surf, f"TASK {self.rnd} OF 3 · {skills.upper()}", (C.WIDTH // 2, 96), 15, gfx.ACCENT, bold=True, mono=True, anchor="center")
        gfx.text(surf, title, (C.WIDTH // 2, 142), 46, gfx.TEXT, bold=True, mono=True, anchor="center")
        gfx.text(surf, "RULE: " + rule, (C.WIDTH // 2, 200), 22, gfx.AMBER, bold=True, anchor="center")
        box = pygame.Rect(200, 240, 880, 250)
        gfx.panel(surf, box, CONSOLE)
        y = 270
        for k, ln in enumerate(lines):
            gfx.text(surf, str(k + 1), (240, y), 22, gfx.ACCENT, bold=True, mono=True)
            y = gfx.text_block(surf, ln, (280, y), 760, 21, gfx.TEXT) + 18
        s = self.app.session
        if s.first_time and self.rnd not in s.practiced:
            gfx.text(surf, "First shift: try one practice round first (P)", (C.WIDTH // 2, 540), 20, gfx.AMBER, bold=True, anchor="center")
        gfx.text(surf, "SPACE start      P practice round      ESC back", (C.WIDTH // 2, 610), 22, gfx.TEXT, bold=True, mono=True, anchor="center")
        footer(surf, "Simple rule · go as fast and accurately as you can")


# =====================================================================
class DebriefScene(Scene):
    LABELS = {"hand_eye": ("HAND-EYE", "click accuracy, clicking speed, laser tracking"), "memory": ("MEMORY", "port order, tracked satellites"),
              "attention": ("ATTENTION", "flash counting while tracking, picking speed")}

    def __init__(self, app):
        super().__init__(app)
        s = self.s = app.session
        pygame.mouse.set_visible(True)
        self.page = 0
        self.scores = scoring.score_session(s.events[1], s.events[2], s.events[3])
        self.ev = readiness.evaluate(self.scores, s.checkin, s.history, s.index)
        self.saved = False
        if not s.practice:
            row = dict(self.scores)
            ev = self.ev
            row.update(astronaut=s.crew, session_index=s.index, timestamp=s.started.isoformat(timespec="seconds"),
                       local_hour=s.started.hour, task_version=C.TASK_VERSION, data_source=s.source, invalid=int(ev["invalid"]),
                       input_device=s.checkin["input_device"], sleep_hours=s.checkin["sleep_hours"], fatigue=s.checkin["fatigue"],
                       stress=s.checkin["stress"], mood=s.checkin["mood"], status=ev["status"], confidence=ev["confidence"],
                       baseline_mode=ev["baseline_mode"], **{c: ev["components"][c]["status"] for c in C.COMPONENTS})
            logger.save_session(row)
            logger.save_events(s.crew, s.index, s.source, s.events[1] + s.events[2] + s.events[3])
            self.saved = True
        self.history = logger.load_history(s.crew)
        app.audio.play("chime" if self.ev["status"] == "GO" else "radio")

    def handle(self, e, now):
        if e.type != pygame.KEYDOWN:
            return
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.app.session = None
            self.app.go(CheckinScene(self.app))
        elif e.key == pygame.K_t:
            self.page = 1 - self.page
        elif e.key == pygame.K_ESCAPE:
            self.app.running = False

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        header(surf, self.app, "SHIFT DEBRIEF", f"{self.s.started:%d %b %Y %H:%M} · input {self.s.checkin['input_device']}")
        (self._main if self.page == 0 else self._details)(surf)
        hint = "ENTER new check-in · T " + ("summary" if self.page else "all numbers") + " · ESC quit · "
        footer(surf, hint + ("saved to data/sessions.csv" if self.saved else "PRACTICE - not saved"))

    def _main(self, surf):
        ev = self.ev
        status = "PRACTICE" if self.s.practice else ev["status"]
        col = gfx.STATUS_COLOR[status]
        card = pygame.Rect(40, 76, 600, 290)
        gfx.panel(surf, card, CONSOLE, col, 14, 2)
        pygame.draw.circle(surf, col, (100, 136), 30)
        gfx.text(surf, status, (150, 104), 40, col, bold=True, mono=True)
        gfx.text(surf, ev["headline"], (150, 148), 20, gfx.TEXT, bold=True)
        y = gfx.text_block(surf, ev["message"], (64, 188), 552, 18, gfx.TEXT)
        for a in ev["advice"][:2]:
            y = gfx.text_block(surf, "› " + a, (64, y + 2), 552, 16, gfx.AMBER)
        cc = {"HIGH": gfx.GREEN, "MEDIUM": gfx.AMBER, "LOW": gfx.RED}[ev["confidence"]]
        r = gfx.pill(surf, f"CONFIDENCE {ev['confidence']}", (64, max(320, y + 6)), cc, 14)
        gfx.text(surf, ev["confidence_why"], (r.right + 10, r.y + 6), 14, gfx.MUTED)

        comp = pygame.Rect(660, 76, 580, 290)
        gfx.panel(surf, comp, CONSOLE)
        gfx.text(surf, "COMPONENT BREAKDOWN · today vs your normal", (680, 90), 13, gfx.MUTED, bold=True, mono=True)
        for k, c in enumerate(C.COMPONENTS):
            y = 130 + k * 76
            st_ = ev["components"][c]["status"]
            ccol = gfx.RED if st_ == "slower" else gfx.GREEN
            pygame.draw.circle(surf, ccol, (688, y + 12), 8)
            name, desc = self.LABELS[c]
            gfx.text(surf, name, (704, y), 20, gfx.TEXT, bold=True, mono=True)
            gfx.text(surf, desc, (704, y + 24), 14, gfx.MUTED)
            lab = st_.upper() if (ev["baseline"] or st_ != "normal") else "NO BASELINE YET"
            gfx.text(surf, lab, (1220, y + 2), 14, ccol, bold=True, mono=True, anchor="topright")
            reasons = ev["components"][c]["reasons"]
            if reasons:
                gfx.text(surf, reasons[0][:58], (1220, y + 24), 12, gfx.AMBER, anchor="topright")

        ctx = pygame.Rect(40, 380, 600, 270)
        gfx.panel(surf, ctx, CONSOLE)
        gfx.text(surf, "KEY NUMBERS", (60, 394), 13, gfx.MUTED, bold=True, mono=True)
        sc = self.scores
        f = lambda v, u="": "-" if v is None else f"{v}{u}"
        items = [("Port order accuracy", f(None if sc["t1_order_acc"] is None else round(sc["t1_order_acc"] * 100), "%")),
                 ("Time between clicks", f(sc["t1_click_time_ms"], " ms")), ("Click error", f(sc["t1_click_err_px"], " px")),
                 ("Satellites found", f"{sc['t2_correct']}/{sc['t2_rounds'] * C.T2_TAGGED}"),
                 ("Laser on target", f(sc["t3_on_target_pct"], "%")), ("Laser error", f(sc["t3_track_err_px"], " px")),
                 ("Green-flash count error", f(sc["t3_count_err"])), ("Perfect port rounds", f"{sc['t1_perfect_rounds']}/{sc['t1_rounds']}")]
        for k, (a, b) in enumerate(items):
            x = 60 + (k % 2) * 290
            yy = 424 + (k // 2) * 52
            gfx.text(surf, a, (x, yy), 14, gfx.MUTED)
            gfx.text(surf, b, (x, yy + 18), 20, gfx.TEXT, bold=True, mono=True)

        tr = pygame.Rect(660, 380, 580, 270)
        gfx.panel(surf, tr, CONSOLE)
        ci = self.s.checkin
        gfx.text(surf, "REPORTED", (680, 394), 13, gfx.MUTED, bold=True, mono=True)
        x = 680
        for chip in (f"Sleep {ci['sleep_hours']:g} h", f"Fatigue {ci['fatigue']}/7", f"Stress {ci['stress']}/5", f"Mood {ci['mood']}/5"):
            x = gfx.pill(surf, chip, (x, 418), gfx.TEXT, 13).right + 8
        yy = 458
        for q in ev["quality"]:
            gfx.text(surf, "Data quality: " + q, (680, yy), 14, gfx.MUTED)
            yy += 22
        for c in ev["context"]:
            gfx.text(surf, "• " + c, (680, yy), 15, gfx.AMBER)
            yy += 22
        self._trend(surf, pygame.Rect(710, max(yy + 24, 520), 500, 100))

    def _trend(self, surf, area):
        pts = [h for h in self.history if h.get("t1_click_time_ms") not in (None, "")][-14:]
        gfx.text(surf, "PORT CLICK TIME TREND (ms)", (area.left - 30, area.top - 24), 12, gfx.DIM, mono=True)
        if len(pts) < 2:
            gfx.text(surf, "More shifts needed for a trend.", area.center, 15, gfx.DIM, anchor="center")
            return
        vals = [float(p["t1_click_time_ms"]) for p in pts]
        lo, hi = min(vals) - 100, max(vals) + 100
        X = lambda i: area.left + i * area.width / (len(pts) - 1)
        Y = lambda v: area.bottom - (v - lo) / (hi - lo) * area.height
        line = [(X(i), Y(v)) for i, v in enumerate(vals)]
        pygame.draw.lines(surf, gfx.MUTED, False, line, 2)
        for i, (p, (x, y)) in enumerate(zip(pts, line)):
            last = i == len(pts) - 1
            col = gfx.ACCENT if last else gfx.TEXT
            if p.get("data_source") == "simulated":
                pygame.draw.circle(surf, gfx.BG, (int(x), int(y)), 5)
                pygame.draw.circle(surf, col, (int(x), int(y)), 5, 2)
            else:
                pygame.draw.circle(surf, col, (int(x), int(y)), 6 if last else 4)

    def _details(self, surf):
        sc = self.scores
        groups = [("PORT SEQUENCE", ["t1_order_acc", "t1_perfect_rounds", "t1_timeouts", "t1_first_click_ms", "t1_click_time_ms", "t1_click_err_px", "t1_empty_clicks"]),
                  ("TRACK THE SATELLITE", ["t2_correct", "t2_accuracy", "t2_perfect_rounds", "t2_select_time_ms", "t2_click_err_px", "t2_timeouts"]),
                  ("STEADY BEAM", ["t3_track_err_px", "t3_on_target_pct", "t3_count_err", "t3_count_correct", "t3_answer_ms"])]
        for j, (t, keys) in enumerate(groups):
            box = pygame.Rect(40 + j * 405, 80, 390, 570)
            gfx.panel(surf, box, CONSOLE)
            gfx.text(surf, t, (box.x + 18, 96), 16, gfx.ACCENT, bold=True, mono=True)
            y = 136
            for k in keys:
                gfx.text(surf, k, (box.x + 18, y), 15, gfx.MUTED, mono=True)
                v = sc.get(k)
                gfx.text(surf, "-" if v is None else str(v), (box.right - 18, y), 16, gfx.TEXT, bold=True, mono=True, anchor="topright")
                y += 44
