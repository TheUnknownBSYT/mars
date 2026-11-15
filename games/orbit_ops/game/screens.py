"""
Non-round screens: check-in, round briefings, rest breaks, mood check,
docking animation and the mission debrief.
"""
import math
import time
from datetime import datetime

import pygame

import config as C
from core import logger, progression, readiness, scoring
from game import gfx
from game.base import Scene, Session, draw_hud, draw_footer
from game.rounds import ROUND_CLASSES

FATIGUE = ["Fully alert", "Very lively", "OK, somewhat fresh", "A little tired",
           "Moderately tired", "Extremely tired", "Completely exhausted"]
STRESS = ["Very low", "Low", "Moderate", "High", "Very high"]
MOOD = ["Very low", "Low", "Neutral", "Good", "Very good"]


# =====================================================================
# Session flow
# =====================================================================
def advance(app):
    """Go to the next step of today's mission check."""
    s = app.session
    s.step += 1
    step = Session.STEPS[s.step]
    if step.startswith("brief"):
        app.go(BriefingScene(app, int(step[-1])))
    elif step.startswith("round"):
        r = int(step[-1])
        app.go(ROUND_CLASSES[r](app, s.schedules[r], practice=False, on_done=lambda: advance(app)))
    elif step.startswith("rest"):
        app.go(BreatherScene(app, int(step[-1])))
    elif step == "mood":
        app.go(MoodScene(app))
    elif step == "dock":
        app.go(DockingScene(app))
    else:
        app.go(DebriefScene(app))


# =====================================================================
# Check-in
# =====================================================================
class CheckinScene(Scene):
    FIELDS = ["crew", "sleep", "fatigue", "stress", "mood", "mode"]

    def __init__(self, app):
        super().__init__(app)
        self.sel = 1
        self.crew = app.crew
        self.sleep = 7.0
        self.fatigue = None
        self.stress = None
        self.mood = None
        self.practice = False
        self.msg = ""
        self.msg_color = gfx.AMBER
        self.confirm_clear = False
        self.refresh()

    def refresh(self):
        self.crew = "".join(ch for ch in self.crew.upper() if ch.isalnum() or ch in "-_")[:12] or "AST-01"
        self.app.crew = self.crew
        self.history = logger.load_history(self.crew)
        self.base = readiness.build_baseline(self.history)

    def handle(self, e, now):
        if e.type != pygame.KEYDOWN:
            return
        f = self.FIELDS[self.sel]
        k = e.key
        if k == pygame.K_ESCAPE:
            self.app.running = False
        elif k in (pygame.K_UP,):
            self.sel = (self.sel - 1) % len(self.FIELDS)
        elif k in (pygame.K_DOWN, pygame.K_TAB):
            self.sel = (self.sel + 1) % len(self.FIELDS)
        elif k == pygame.K_F2:
            logger.make_demo_history(self.crew)
            self.refresh()
            self.msg, self.msg_color = f"Loaded 8 SIMULATED sessions for {self.crew} (tagged data_source=simulated).", gfx.ACCENT
        elif k == pygame.K_F3:
            if self.confirm_clear:
                logger.clear_astronaut(self.crew)
                self.refresh()
                self.msg, self.msg_color = f"History cleared for {self.crew}.", gfx.ACCENT
                self.confirm_clear = False
            else:
                self.confirm_clear = True
                self.msg, self.msg_color = f"Press F3 again to delete ALL saved sessions for {self.crew}.", gfx.RED
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
            elif f == "fatigue":
                self.fatigue = min(7, max(1, (self.fatigue or 3) + (d if self.fatigue else 0)))
            elif f == "stress":
                self.stress = min(5, max(1, (self.stress or 2) + (d if self.stress else 0)))
            elif f == "mood":
                self.mood = min(5, max(1, (self.mood or 3) + (d if self.mood else 0)))
            elif f == "mode":
                self.practice = not self.practice
        elif e.unicode and e.unicode.isdigit() and f in ("fatigue", "stress", "mood"):
            v = int(e.unicode)
            hi = 7 if f == "fatigue" else 5
            if 1 <= v <= hi:
                setattr(self, f, v)

    def start(self):
        missing = [n for n in ("fatigue", "stress", "mood") if getattr(self, n) is None]
        if missing:
            self.msg, self.msg_color = "Please rate your " + ", ".join(missing) + " (use LEFT/RIGHT or number keys).", gfx.AMBER
            return
        checkin = {"sleep_hours": self.sleep, "fatigue": self.fatigue, "stress": self.stress, "mood_pre": self.mood}
        self.app.session = Session(self.crew, checkin, practice_mode=self.practice)
        advance(self.app)

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        gfx.earth(surf, (1180, 820), 300)
        draw_hud(surf, self.app, "DAILY READINESS CHECK", "pre-mission check-in", show_progress=False)
        gfx.text(surf, "Good morning, pilot.", (60, 92), 40, gfx.TEXT, bold=True)
        gfx.text(surf, "Three short tasks (~4 min) measure your reaction time: alertness, decision and adaptation.",
                 (60, 140), 20, gfx.MUTED)

        box = pygame.Rect(50, 180, 640, 440)
        gfx.panel(surf, box, gfx.PANEL, gfx.LINE, 16)
        rows = [
            ("crew", "CREW ID", self.crew + ("_" if self.sel == 0 and int(now * 2) % 2 == 0 else ""), "type to change"),
            ("sleep", "SLEEP LAST NIGHT", f"{self.sleep:.1f} h", ""),
            ("fatigue", "FATIGUE NOW (1-7)", self._val(self.fatigue, FATIGUE), ""),
            ("stress", "STRESS (1-5)", self._val(self.stress, STRESS), ""),
            ("mood", "MOOD (1-5)", self._val(self.mood, MOOD), ""),
            ("mode", "MODE", "PRACTICE (not saved)" if self.practice else "MISSION (saved)", ""),
        ]
        y = 200
        for i, (key, label, value, hint) in enumerate(rows):
            r = pygame.Rect(66, y, 608, 62)
            active = i == self.sel
            if active:
                gfx.panel(surf, r, gfx.PANEL2, gfx.ACCENT, 10, 2)
            gfx.text(surf, label, (84, y + 10), 15, gfx.MUTED, bold=True, mono=True)
            col = gfx.TEXT if "rate" not in value else gfx.DIM
            gfx.text(surf, value, (84, y + 30), 24, col, bold=True)
            if key in ("sleep", "fatigue", "stress", "mood", "mode") and active:
                gfx.text(surf, "<  >", (650, y + 31), 20, gfx.ACCENT, bold=True, mono=True, anchor="topright")
            if key == "fatigue" and self.fatigue:
                self._dots(surf, (420, y + 38), self.fatigue, 7)
            if key == "stress" and self.stress:
                self._dots(surf, (420, y + 38), self.stress, 5)
            if key == "mood" and self.mood:
                self._face(surf, (560, y + 32), self.mood)
            if hint and active:
                gfx.text(surf, hint, (650, y + 12), 14, gfx.DIM, mono=True, anchor="topright")
            y += 68

        # right column - crew record
        rbox = pygame.Rect(720, 180, 510, 270)
        gfx.panel(surf, rbox, gfx.PANEL, gfx.LINE, 16)
        gfx.text(surf, "CREW RECORD", (744, 198), 16, gfx.MUTED, bold=True, mono=True)
        n = len(self.history)
        nsim = sum(1 for h in self.history if h.get("data_source") == "simulated")
        rank, nxt = progression.rank_for(n)
        gfx.text(surf, rank.upper(), (744, 226), 30, gfx.ACCENT, bold=True)
        lines = [f"{n} saved sessions" + (f"  ({nsim} simulated)" if nsim else ""),
                 f"Station modules: {len(progression.modules_for(n))}/{len(C.STATION_MODULES)}"]
        if n < C.FAMILIARISATION_SESSIONS:
            lines.append(f"Familiarisation: {n}/{C.FAMILIARISATION_SESSIONS} sessions (learning the game)")
        elif self.base:
            lines.append(f"Personal baseline: ACTIVE ({self.base['n']} sessions)")
        else:
            lines.append("Personal baseline: forming (needs 3 sessions after familiarisation)")
        if self.history:
            last = self.history[-1]
            lines.append(f"Last result: {last.get('status', '-')}   ({str(last.get('timestamp', ''))[:10]})")
        yy = 270
        for ln in lines:
            gfx.text(surf, ln, (744, yy), 19, gfx.TEXT)
            yy += 30
        gfx.station(surf, (1060, 420), 0.45, len(progression.modules_for(n)))

        # right column - today's mission
        mbox = pygame.Rect(720, 465, 510, 155)
        gfx.panel(surf, mbox, gfx.PANEL, gfx.LINE, 16)
        gfx.text(surf, "TODAY'S MISSION", (744, 480), 16, gfx.MUTED, bold=True, mono=True)
        for j, (name, what) in enumerate([("1  MASTER ALARM", "alertness"), ("2  DEBRIS WATCH", "decision + self-control"),
                                          ("3  MISSION CONTROL ORDERS", "adaptation")]):
            gfx.text(surf, name, (744, 510 + j * 34), 20, gfx.TEXT, bold=True)
            gfx.text(surf, what, (1210, 512 + j * 34), 17, gfx.MUTED, anchor="topright")

        if self.msg:
            gfx.text(surf, self.msg, (60, 632), 18, self.msg_color)
        draw_footer(surf, "UP/DOWN select   LEFT/RIGHT or 1-7 set   ENTER start   F2 demo history   F3 clear history   F11 fullscreen   ESC quit")

    @staticmethod
    def _val(v, labels):
        return f"{v} - {labels[v - 1]}" if v else "-- rate --"

    @staticmethod
    def _dots(surf, pos, v, n):
        for i in range(n):
            col = gfx.ACCENT if i < v else gfx.LINE
            pygame.draw.circle(surf, col, (pos[0] + i * 18, pos[1]), 6)

    @staticmethod
    def _face(surf, c, mood):
        pygame.draw.circle(surf, gfx.AMBER, c, 18, 2)
        pygame.draw.circle(surf, gfx.AMBER, (c[0] - 6, c[1] - 5), 2)
        pygame.draw.circle(surf, gfx.AMBER, (c[0] + 6, c[1] - 5), 2)
        curve = (mood - 3) * 4      # -8 .. +8
        pts = [(c[0] - 8, c[1] + 6), (c[0], c[1] + 6 + curve), (c[0] + 8, c[1] + 6)]
        pygame.draw.lines(surf, gfx.AMBER, False, pts, 2)


# =====================================================================
# Round briefing
# =====================================================================
BRIEFS = {
    1: ("MASTER ALARM", "ALERTNESS",
        ["Watch the master alarm in the cockpit.",
         "At a random moment it lights up red and a counter starts.",
         "Press SPACE as fast as you can to stop it.",
         "Don't guess - pressing before it lights up is a FALSE START."],
        ["SPACE"], "reaction time, lapses (>= 355 ms), false starts - same rules as NASA's PVT-B"),
    2: ("DEBRIS WATCH", "DECISION + SELF-CONTROL",
        ["Objects appear on the radar one at a time.",
         "DEBRIS (red, jagged): press SPACE to fire the laser.",
         "SATELLITE (green, with panels): HOLD FIRE - do nothing.",
         "Be fast, but never shoot a friendly satellite."],
        ["SPACE"], "choice reaction time, friendly-fire errors, misses"),
    3: ("MISSION CONTROL ORDERS", "ADAPTATION",
        ["Mission Control tells you to sort targets BY SHAPE or BY COLOR.",
         f"SHAPE:  triangle = {C.R3_LEFT_KEY_NAME}     circle = {C.R3_RIGHT_KEY_NAME}",
         f"COLOR:  orange = {C.R3_LEFT_KEY_NAME}     blue = {C.R3_RIGHT_KEY_NAME}",
         "The orders change without warning - a banner announces each change."],
        [C.R3_LEFT_KEY_NAME, C.R3_RIGHT_KEY_NAME], "switch cost (extra time after a rule change), old-rule errors"),
}


class BriefingScene(Scene):
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
            s.practiced.add(self.rnd)
            back = lambda: self.app.go(BriefingScene(self.app, self.rnd))
            self.app.go(ROUND_CLASSES[self.rnd](self.app, s.practice_schedule(self.rnd), practice=True, on_done=back))
        elif e.key == pygame.K_ESCAPE:
            self.app.session = None
            self.app.go(CheckinScene(self.app))

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        title, skill, lines, keys, measures = BRIEFS[self.rnd]
        draw_hud(surf, self.app, "MISSION BRIEFING", f"ROUND {self.rnd} OF 3")
        gfx.text(surf, f"ROUND {self.rnd} OF 3  -  {skill}", (C.WIDTH // 2, 112), 20, gfx.ACCENT, bold=True, mono=True, anchor="center")
        gfx.text(surf, title, (C.WIDTH // 2, 160), 54, gfx.TEXT, bold=True, anchor="center")
        box = pygame.Rect(240, 210, 800, 250)
        gfx.panel(surf, box)
        y = 232
        for ln in lines:
            pygame.draw.circle(surf, gfx.ACCENT, (272, y + 12), 4)
            gfx.text(surf, ln, (290, y), 23, gfx.TEXT)
            y += 50
        # illustration
        if self.rnd == 1:
            gfx.alarm_light(surf, (930, 330), 40, True, label="")
        elif self.rnd == 2:
            gfx.debris(surf, (905, 300), 26, 3)
            gfx.satellite(surf, (975, 390), 24)
        x = C.WIDTH // 2 - (len(keys) - 1) * 50
        for k in keys:
            gfx.key_cap(surf, k, (x, 500), 30)
            x += 100
        gfx.text(surf, "Measures: " + measures, (C.WIDTH // 2, 548), 18, gfx.MUTED, anchor="center")
        s = self.app.session
        if s.first_time and self.rnd not in s.practiced:
            gfx.text(surf, "First mission - practise first:  press P", (C.WIDTH // 2, 592), 22, gfx.AMBER, bold=True, anchor="center")
        pulse = 0.5 + 0.5 * math.sin(now * 4)
        col = tuple(int(a + (b - a) * pulse) for a, b in zip(gfx.ACCENT, gfx.WHITE))
        gfx.text(surf, "Press SPACE to start the round", (C.WIDTH // 2, 636), 26, col, bold=True, anchor="center")
        draw_footer(surf, "SPACE start   P practice (not scored)   ESC back to check-in")


# =====================================================================
# Rest between rounds
# =====================================================================
class BreatherScene(Scene):
    def __init__(self, app, finished_round):
        super().__init__(app)
        self.r = finished_round
        self.t0 = time.perf_counter()
        res = app.session.results[finished_round]
        if finished_round == 1:
            sc = scoring.score_round1(res)
            self.summary = f"Median reaction {sc['r1_median_ms'] or '-'} ms   |   lapses {sc['r1_lapses']}   |   false starts {sc['r1_false_starts']}"
        else:
            sc = scoring.score_round2(res)
            self.summary = f"Debris cleared {sc['r2_hits']}   |   satellites protected {sc['r2_correct_holds']}   |   friendly fire {sc['r2_false_alarms']}"
        app.audio.play("chime")

    def handle(self, e, now):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE and now - self.t0 > C.BREATHER_S * 0.6:
            advance(self.app)

    def update(self, now, dt):
        self.app.stars.update(dt, 40)
        if now - self.t0 >= C.BREATHER_S:
            advance(self.app)

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        draw_hud(surf, self.app, "CRUISE PHASE", "rest your hands")
        p = self.app.session.progress()
        gfx.earth(surf, (200, 760), 260)
        gfx.station(surf, (1020, 300), 0.9)
        cx = 300 + 560 * p
        gfx.capsule(surf, (int(cx), 330), 1.4, thrust=0.6 + 0.3 * math.sin(now * 20))
        gfx.text(surf, f"ROUND {self.r} COMPLETE", (C.WIDTH // 2, 470), 40, gfx.GREEN, bold=True, anchor="center")
        gfx.text(surf, self.summary, (C.WIDTH // 2, 520), 22, gfx.TEXT, anchor="center")
        left = max(0, C.BREATHER_S - (now - self.t0))
        breath = "breathe in..." if math.sin(now * math.pi / 2.5) > 0 else "breathe out..."
        gfx.text(surf, f"Relax your hands and {breath}   next round in {left:0.0f} s",
                 (C.WIDTH // 2, 580), 20, gfx.MUTED, anchor="center")


# =====================================================================
# Mood after the mission
# =====================================================================
class MoodScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.v = app.session.checkin.get("mood_pre") or 3

    def handle(self, e, now):
        if e.type != pygame.KEYDOWN:
            return
        if e.key == pygame.K_LEFT:
            self.v = max(1, self.v - 1)
        elif e.key == pygame.K_RIGHT:
            self.v = min(5, self.v + 1)
        elif e.unicode and e.unicode in "12345":
            self.v = int(e.unicode)
        elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
            self.app.session.mood_post = self.v
            advance(self.app)

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        draw_hud(surf, self.app, "FINAL APPROACH", "quick check")
        gfx.text(surf, "All three rounds complete!", (C.WIDTH // 2, 190), 44, gfx.GREEN, bold=True, anchor="center")
        gfx.text(surf, "How do you feel right now?", (C.WIDTH // 2, 260), 30, gfx.TEXT, anchor="center")
        for i in range(1, 6):
            x = C.WIDTH // 2 + (i - 3) * 150
            sel = i == self.v
            r = pygame.Rect(0, 0, 120, 140)
            r.center = (x, 400)
            gfx.panel(surf, r, gfx.PANEL2 if sel else gfx.PANEL, gfx.ACCENT if sel else gfx.LINE, 14, 2 if sel else 1)
            c = (x, 380)
            col = gfx.AMBER if sel else gfx.MUTED
            pygame.draw.circle(surf, col, c, 30, 3)
            pygame.draw.circle(surf, col, (c[0] - 10, c[1] - 8), 3)
            pygame.draw.circle(surf, col, (c[0] + 10, c[1] - 8), 3)
            curve = (i - 3) * 6
            pygame.draw.lines(surf, col, False, [(c[0] - 13, c[1] + 10), (c[0], c[1] + 10 + curve), (c[0] + 13, c[1] + 10)], 3)
            gfx.text(surf, MOOD[i - 1], (x, 445), 16, col, bold=sel, anchor="center")
        draw_footer(surf, "LEFT/RIGHT or 1-5 choose    ENTER confirm")


# =====================================================================
# Docking animation (reward)
# =====================================================================
class DockingScene(Scene):
    DUR = 3.6

    def __init__(self, app):
        super().__init__(app)
        self.t0 = time.perf_counter()
        self.played = False
        hist = app.session.history
        self.modules = len(progression.modules_for(len(hist) + 1))

    def handle(self, e, now):
        if e.type == pygame.KEYDOWN and now - self.t0 > 1.0:
            advance(self.app)

    def update(self, now, dt):
        self.app.stars.update(dt, 8)
        if not self.played and now - self.t0 > self.DUR * 0.75:
            self.app.audio.play("dock")
            self.played = True
        if now - self.t0 >= self.DUR + 1.2:
            advance(self.app)

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        gfx.earth(surf, (640, 1050), 560)
        p = min(1.0, (now - self.t0) / self.DUR)
        ease = 1 - (1 - p) ** 3
        st_x, st_y = 760, 300
        gfx.station(surf, (st_x, st_y), 1.3, self.modules)
        port = (st_x + 90 * 1.3, st_y)
        cap_x = 120 + (port[0] - 120 + 45) * ease
        gfx.capsule(surf, (int(cap_x), st_y), 1.2, thrust=0 if p >= 1 else 0.5, facing=-1)
        if p >= 1:
            gfx.text(surf, "DOCKING COMPLETE", (640, 520), 50, gfx.GREEN, bold=True, anchor="center")
            gfx.text(surf, "Welcome aboard. Preparing your debrief...", (640, 570), 22, gfx.TEXT, anchor="center")
        else:
            gfx.text(surf, f"CLOSING  {12 * (1 - ease):4.1f} km -> {max(0, 50 * (1 - ease)):4.0f} m",
                     (640, 540), 22, gfx.MUTED, mono=True, anchor="center")


# =====================================================================
# Debrief
# =====================================================================
class DebriefScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.session
        self.s = s
        self.page = 0
        self.scores = scoring.score_session(s.results[1], s.results[2], s.results[3])
        self.ev = readiness.evaluate(self.scores, s.checkin, s.history, s.index)
        self.prog = None
        self.saved_to = None
        if not s.practice_mode:
            row = self._row()
            logger.save_session(row)
            all_trials = s.results[1] + s.results[2] + s.results[3]
            logger.save_trials(s.crew, s.index, s.data_source, all_trials)
            self.prog = progression.update(s.crew, self.scores, s.history)
            self.saved_to = C.SESSIONS_CSV
        self.history = logger.load_history(s.crew)
        app.audio.play("chime" if self.ev["status"] == "GO" else "radio")

    def _row(self):
        s, ev = self.s, self.ev
        row = dict(self.scores)
        row.update(
            astronaut=s.crew, session_index=s.index,
            timestamp=s.started.isoformat(timespec="seconds"), local_hour=s.started.hour,
            task_version=C.TASK_VERSION, data_source=s.data_source, invalid=int(ev["invalid"]),
            sleep_hours=s.checkin["sleep_hours"], fatigue=s.checkin["fatigue"],
            stress=s.checkin["stress"], mood_pre=s.checkin["mood_pre"], mood_post=s.mood_post,
            alertness=ev["components"]["alertness"]["status"],
            decision=ev["components"]["decision"]["status"],
            adaptation=ev["components"]["adaptation"]["status"],
            status=ev["status"], confidence=ev["confidence"], baseline_mode=ev["baseline_mode"],
        )
        return row

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

    # ------------------------------------------------------------ drawing
    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        sub = f"{self.s.started:%d %b %Y  %H:%M}"
        draw_hud(surf, self.app, "MISSION DEBRIEF", sub, show_progress=False)
        if self.page == 0:
            self._draw_main(surf, now)
        else:
            self._draw_details(surf)
        hint = "ENTER new check-in    T " + ("summary" if self.page else "all numbers") + "    ESC quit"
        if self.saved_to:
            hint += f"    saved to data/{self.saved_to.name}"
        else:
            hint += "    PRACTICE - not saved"
        draw_footer(surf, hint)

    def _draw_main(self, surf, now):
        ev = self.ev
        status = "PRACTICE" if self.s.practice_mode else ev["status"]
        col = gfx.STATUS_COLOR[status]
        # ---- status card
        card = pygame.Rect(40, 84, 600, 300)
        gfx.panel(surf, card, gfx.PANEL, col, 18, 2)
        gfx.glow_circle(surf, col, (110, 160), 38, strength=70)
        pygame.draw.circle(surf, col, (110, 160), 38)
        gfx.text(surf, status, (170, 112), 44, col, bold=True)
        gfx.text(surf, ev["headline"], (170, 160), 24, gfx.TEXT, bold=True)
        y = gfx.text_block(surf, ev["message"], (64, 214), 556, 20, gfx.TEXT)
        for adv in ev["advice"]:
            y = gfx.text_block(surf, "> " + adv, (64, y + 4), 556, 18, gfx.AMBER)
        conf_col = {"HIGH": gfx.GREEN, "MEDIUM": gfx.AMBER, "LOW": gfx.RED}[ev["confidence"]]
        py = max(340, y + 8)
        r = gfx.pill(surf, f"CONFIDENCE {ev['confidence']}", (64, py), conf_col, 15)
        gfx.text(surf, ev["confidence_why"], (r.right + 12, py + 5), 15, gfx.MUTED)

        # ---- breakdown
        bx = pygame.Rect(660, 84, 580, 300)
        gfx.panel(surf, bx)
        gfx.text(surf, "REACTION-TIME BREAKDOWN", (684, 100), 16, gfx.MUTED, bold=True, mono=True)
        gfx.text(surf, "today vs your normal", (1216, 102), 15, gfx.DIM, anchor="topright")
        sc = self.scores
        comps = [
            ("ALERTNESS", "alertness", sc.get("r1_median_ms"), "Round 1 median reaction"),
            ("DECISION", "decision", sc.get("decision_time_ms"), "Round 2 extra time to choose"),
            ("ADAPTATION", "adaptation", sc.get("switch_cost_ms"), "Round 3 switch cost"),
        ]
        for j, (name, key, val, desc) in enumerate(comps):
            y = 138 + j * 80
            c = ev["components"][key]
            ccol = gfx.COMP_COLOR.get(c["status"], gfx.MUTED)
            pygame.draw.circle(surf, ccol, (694, y + 14), 8)
            gfx.text(surf, name, (712, y), 22, gfx.TEXT, bold=True)
            gfx.text(surf, desc, (712, y + 26), 15, gfx.MUTED)
            gfx.text(surf, f"{val} ms" if val is not None else "-", (1000, y + 2), 22, gfx.TEXT, bold=True, mono=True, anchor="topright")
            label = c["status"].upper() if ev["mode"] == "personal" or c["status"] != "normal" else "NO BASELINE YET"
            gfx.text(surf, label, (1216, y + 4), 15, ccol, bold=True, mono=True, anchor="topright")
            # delta bar: centre = your normal, right = slower
            bar = pygame.Rect(1030, y + 32, 186, 10)
            pygame.draw.rect(surf, gfx.LINE, bar, border_radius=5)
            mid = bar.centerx
            pygame.draw.line(surf, gfx.TEXT, (mid, bar.top - 4), (mid, bar.bottom + 4), 2)
            d = c.get("delta")
            if d is not None:
                w = int(max(-1, min(1, d / 150)) * (bar.width // 2))
                r = pygame.Rect(min(mid, mid + w), bar.top, abs(w), bar.height)
                pygame.draw.rect(surf, gfx.RED if d > 0 else gfx.GREEN, r, border_radius=5)
                gfx.text(surf, f"{d:+.0f} ms", (1030, y + 46), 13, gfx.MUTED, mono=True)

        # ---- context + progression
        cx = pygame.Rect(40, 400, 600, 250)
        gfx.panel(surf, cx)
        gfx.text(surf, "WHAT YOU REPORTED", (64, 416), 16, gfx.MUTED, bold=True, mono=True)
        ci = self.s.checkin
        chips = [f"Sleep {ci['sleep_hours']:g} h", f"Fatigue {ci['fatigue']}/7", f"Stress {ci['stress']}/5",
                 f"Mood {ci['mood_pre']} -> {self.s.mood_post}"]
        x = 64
        for ch in chips:
            r = gfx.pill(surf, ch, (x, 446), gfx.TEXT, 15)
            x = r.right + 10
        y = 490
        for q in ev["quality"]:
            y = gfx.text_block(surf, "Data quality: " + q, (64, y), 556, 17, gfx.MUTED) + 2
        for c in ev["context"]:
            gfx.text(surf, "- " + c, (64, y), 17, gfx.AMBER)
            y += 24
        if self.prog:
            p = self.prog
            gfx.text(surf, f"RANK  {p['rank'].upper()}", (64, 580), 20, gfx.ACCENT, bold=True)
            nr = f"   next: {p['next_rank'][1]} at {p['next_rank'][0]} sessions" if p["next_rank"] else ""
            gfx.text(surf, f"{p['sessions_done']} sessions   streak {p['streak']} day(s){nr}", (64, 608), 16, gfx.MUTED)
            extra = []
            if p["new_badges"]:
                extra.append("NEW BADGE: " + ", ".join(b[0] for b in p["new_badges"]))
            if p["new_module"]:
                extra.append(f"STATION MODULE UNLOCKED: {p['new_module']}")
            if extra:
                gfx.text(surf, "   ".join(extra), (64, 630), 16, gfx.GREEN, bold=True)
        elif self.s.practice_mode:
            gfx.text(surf, "Practice run - nothing saved, no baseline update.", (64, 590), 18, gfx.ACCENT)

        # ---- trend
        tr = pygame.Rect(660, 400, 580, 250)
        gfx.panel(surf, tr)
        gfx.text(surf, "ALERTNESS TREND  (Round 1 median, ms)", (684, 416), 16, gfx.MUTED, bold=True, mono=True)
        self._trend(surf, pygame.Rect(700, 450, 520, 170))

    def _trend(self, surf, area):
        pts = [h for h in self.history if h.get("r1_median_ms") not in (None, "")][-14:]
        if self.s.practice_mode:
            pts = pts + [{"r1_median_ms": self.scores.get("r1_median_ms"), "data_source": "practice", "session_index": "P"}]
        pts = [p for p in pts if p.get("r1_median_ms") not in (None, "")]
        if len(pts) < 2:
            gfx.text(surf, "Play at least 2 sessions to see your trend.", area.center, 18, gfx.DIM, anchor="center")
            return
        vals = [float(p["r1_median_ms"]) for p in pts]
        base = readiness.build_baseline(self.s.history)
        band = None
        if base and "r1_median_ms" in base:
            b = base["r1_median_ms"]
            band = (b["centre"] - 2 * b["spread"], b["centre"] + 2 * b["spread"], b["centre"])
            vals += [band[0], band[1]]
        lo, hi = min(vals) - 15, max(vals) + 15
        X = lambda i: area.left + i * area.width / (len(pts) - 1)
        Y = lambda v: area.bottom - (v - lo) / (hi - lo) * area.height
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            pygame.draw.line(surf, (24, 34, 58), (area.left, Y(v)), (area.right, Y(v)), 1)
            gfx.text(surf, f"{v:.0f}", (area.left - 6, Y(v)), 12, gfx.DIM, mono=True, anchor="midright")
        if band:
            r = pygame.Rect(area.left, Y(band[1]), area.width, Y(band[0]) - Y(band[1]))
            sh = pygame.Surface(r.size, pygame.SRCALPHA)
            sh.fill((79, 209, 255, 30))
            surf.blit(sh, r.topleft)
            pygame.draw.line(surf, (79, 209, 255), (area.left, Y(band[2])), (area.right, Y(band[2])), 1)
        line = [(X(i), Y(float(p["r1_median_ms"]))) for i, p in enumerate(pts)]
        pygame.draw.lines(surf, gfx.MUTED, False, line, 2)
        for i, (p, (x, y)) in enumerate(zip(pts, line)):
            last = i == len(pts) - 1
            col = gfx.ACCENT if last else gfx.TEXT
            if p.get("data_source") == "simulated":
                pygame.draw.circle(surf, gfx.BG, (int(x), int(y)), 5)
                pygame.draw.circle(surf, col, (int(x), int(y)), 5, 2)
            else:
                pygame.draw.circle(surf, col, (int(x), int(y)), 7 if last else 5)
            gfx.text(surf, str(p.get("session_index", "")), (x, area.bottom + 8), 12, gfx.DIM, mono=True, anchor="midtop")
        gfx.text(surf, "o simulated   * real   band = your normal +/-2 SD", (area.right, area.top - 22), 12, gfx.DIM, anchor="topright")

    def _draw_details(self, surf):
        sc = self.scores
        cols = [
            ("ROUND 1 - ALERTNESS", [("Median RT", "r1_median_ms", "ms"), ("Mean RT", "r1_mean_ms", "ms"),
                                     ("Variability (SD)", "r1_sd_ms", "ms"), ("Response speed 1/RT", "r1_speed", "/s"),
                                     ("Fastest 10%", "r1_fast10_ms", "ms"), ("Slowest 10%", "r1_slow10_ms", "ms"),
                                     ("Lapses (>=355 ms + misses)", "r1_lapses", ""), ("False starts", "r1_false_starts", ""),
                                     ("Time-on-task slowing", "r1_time_on_task_ms", "ms")]),
            ("ROUND 2 - DECISION", [("Go reaction (median)", "r2_go_rt_ms", "ms"), ("Decision time (R2 - R1)", "decision_time_ms", "ms"),
                                    ("Debris cleared", "r2_hits", ""), ("Debris missed", "r2_misses", ""),
                                    ("Friendly fire", "r2_false_alarms", ""), ("Satellites protected", "r2_correct_holds", ""),
                                    ("Accuracy", "r2_accuracy", "%")]),
            ("ROUND 3 - ADAPTATION", [("RT after switch", "r3_switch_rt_ms", "ms"), ("RT on repeat", "r3_repeat_rt_ms", "ms"),
                                      ("Switch cost", "switch_cost_ms", "ms"), ("Accuracy", "r3_accuracy", "%"),
                                      ("Accuracy on switches", "r3_switch_accuracy", "%"), ("Old-rule errors", "r3_old_rule_errors", ""),
                                      ("Timeouts", "r3_timeouts", "")]),
        ]
        for j, (title, items) in enumerate(cols):
            x = 40 + j * 405
            box = pygame.Rect(x, 90, 390, 560)
            gfx.panel(surf, box)
            gfx.text(surf, title, (x + 20, 108), 17, gfx.ACCENT, bold=True, mono=True)
            y = 150
            for label, key, unit in items:
                v = sc.get(key)
                if v is None:
                    s = "-"
                elif unit == "%":
                    s = f"{v * 100:.0f}%"
                else:
                    s = f"{v} {unit}".strip()
                gfx.text(surf, label, (x + 20, y), 18, gfx.MUTED)
                gfx.text(surf, s, (x + 370, y), 19, gfx.TEXT, bold=True, mono=True, anchor="topright")
                pygame.draw.line(surf, (24, 34, 58), (x + 20, y + 30), (x + 370, y + 30), 1)
                y += 44
