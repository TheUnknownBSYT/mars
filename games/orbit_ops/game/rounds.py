"""
The three reaction-time rounds.

Timing rules (keep these if you edit anything!):
  * stimulus onset = time the frame was actually flipped to the screen (on_flip)
  * key time       = perf_counter() taken by main.py right before reading events,
                     with the loop polling ~1000x per second during rounds
  * sounds play only AFTER a response, never at stimulus onset
"""
import math
from datetime import datetime

import pygame

import config as C
from game import gfx
from game.base import Scene, draw_hud, draw_footer


class RoundScene(Scene):
    precise = True
    number = 0
    title = ""

    def __init__(self, app, trials, practice=False, on_done=None):
        super().__init__(app)
        self.trials = [dict(t) for t in trials]
        self.practice = practice
        self.on_done = on_done
        self.results = []
        self.i = 0
        self.state = None
        self.state_end = 0.0
        self.onset = None
        self.onset_pending = False
        self.feedback = None          # (text, color, subtext)
        self.after_feedback = "next"  # or "repeat"
        self.paused = False
        self.particles = gfx.Particles()
        self.repeats = 0
        self.started = False

    # ------------------------------------------------------------ helpers
    @property
    def trial(self):
        return self.trials[self.i]

    def set_state(self, state, now, duration=0.0):
        self.state = state
        self.state_end = now + duration
        self.redraw = True

    def begin_trial(self, now):
        self.feedback = None
        self.set_state("isi", now, self.trial["isi_s"])

    def restart_trial(self, now):
        """Same trial again after an early press (new random wait)."""
        self.begin_trial(now)

    def show_stimulus(self):
        self.state = "stim"
        self.onset = None
        self.onset_pending = True
        self.redraw = True

    def on_flip(self, t):
        if self.onset_pending:
            self.onset = t
            self.onset_pending = False

    def rt_ms(self, now):
        return (now - (self.onset if self.onset is not None else now)) * 1000.0

    def record(self, response, correct, rt=None, key="", counts=True, **extra):
        row = {k: self.trial.get(k) for k in ("round", "trial", "condition", "rule", "is_switch",
                                               "congruent", "stimulus", "isi_s")}
        row.update(response=response, correct=int(bool(correct)), rt_ms=rt, key=key,
                   timestamp=datetime.now().isoformat(timespec="milliseconds"), **extra)
        self.results.append(row)
        if counts and not self.practice and self.app.session:
            self.app.session.done += 1

    def give_feedback(self, now, text, color, sub="", dur=0.5, then="next"):
        self.feedback = (text, color, sub)
        self.after_feedback = then
        self.set_state("feedback", now, dur)

    def finish(self):
        if not self.practice and self.app.session:
            self.app.session.results[self.number] = self.results
        if self.on_done:
            self.on_done()

    # ------------------------------------------------------------ loop
    def handle(self, e, now):
        if e.type != pygame.KEYDOWN:
            return
        if e.key == pygame.K_ESCAPE:
            self.paused = not self.paused
            self.redraw = True
            if not self.paused:
                self.begin_trial(now)            # restart the interrupted trial cleanly
            return
        if self.paused:
            if e.key == pygame.K_q:
                from game.screens import CheckinScene
                self.app.session = None
                self.app.go(CheckinScene(self.app))
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.paused = False
                self.begin_trial(now)
            return
        if self.started:
            self.on_key(e.key, now)

    def update(self, now, dt):
        self.particles.update(dt)
        if not self.started:
            self.started = True
            self.begin_trial(now)
            return
        if self.paused:
            return
        if self.state in ("isi",) and now >= self.state_end:
            self.show_stimulus()
        elif self.state == "stim" and self.onset is not None and now - self.onset >= self.window():
            self.on_timeout(now)
        elif self.state == "feedback" and now >= self.state_end:
            if self.after_feedback == "repeat" and self.repeats < 3:
                self.repeats += 1
                if self.app.session:
                    self.trial["isi_s"] = self.app.session.rng.uniform(*self.isi_range())
                self.restart_trial(now)
            else:
                self.repeats = 0
                self.i += 1
                if self.i >= len(self.trials):
                    self.finish()
                else:
                    self.begin_trial(now)
        elif self.state == "banner" and now >= self.state_end:
            self.set_state("isi", now, self.trial["isi_s"])

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        self.app.stars.draw(surf)
        sub = ("PRACTICE - not scored   " if self.practice else "") + \
              f"TRIAL {min(self.i + 1, len(self.trials))}/{len(self.trials)}"
        draw_hud(surf, self.app, f"ROUND {self.number} - {self.title}", sub, show_progress=not self.practice)
        self.draw_round(surf, now)
        self.particles.draw(surf)
        if self.paused:
            veil = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
            veil.fill((4, 8, 16, 220))
            surf.blit(veil, (0, 0))
            gfx.text(surf, "MISSION PAUSED", (C.WIDTH // 2, 300), 44, gfx.AMBER, bold=True, anchor="center")
            gfx.text(surf, "ENTER = resume (current trial restarts)     Q = abort session (nothing saved)",
                     (C.WIDTH // 2, 360), 22, gfx.TEXT, anchor="center")

    # ------------------------------------------------------------ for subclasses
    def window(self):
        raise NotImplementedError

    def isi_range(self):
        raise NotImplementedError

    def on_key(self, key, now):
        raise NotImplementedError

    def on_timeout(self, now):
        raise NotImplementedError

    def draw_round(self, surf, now):
        raise NotImplementedError


# =====================================================================
# ROUND 1 - MASTER ALARM  (alertness, PVT-B rules)
# =====================================================================
class MasterAlarmRound(RoundScene):
    number = 1
    title = "MASTER ALARM"
    CENTER = (640, 360)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.streak = 0
        self.best_streak = 0
        self.last_rt = None

    def window(self):
        return C.R1_TIMEOUT_S

    def isi_range(self):
        return C.R1_ISI_S

    def on_key(self, key, now):
        if key != pygame.K_SPACE:
            return
        if self.state == "isi":
            self.record("false_start", False, None, "space", counts=False)
            self.streak = 0
            self.app.audio.play("error")
            self.give_feedback(now, "TOO EARLY", gfx.RED, "wait for the alarm", 0.8, then="repeat")
        elif self.state == "stim":
            rt = self.rt_ms(now)
            if rt < C.FALSE_START_MS:
                self.record("false_start", False, rt, "space")
                self.streak = 0
                self.app.audio.play("error")
                self.give_feedback(now, "TOO EARLY", gfx.RED, "anticipation", 0.8)
                return
            lapse = rt >= C.R1_LAPSE_MS
            self.record("hit", True, rt, "space", lapse=int(lapse))
            self.last_rt = rt
            if lapse:
                self.streak = 0
                self.app.audio.play("lapse")
            else:
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                self.app.audio.play("hit")
            self.give_feedback(now, f"{rt:.0f} ms", gfx.AMBER if lapse else gfx.GREEN,
                               "LAPSE" if lapse else "", C.R1_FEEDBACK_S)

    def on_timeout(self, now):
        self.record("miss", False, None, "", lapse=1)
        self.streak = 0
        self.app.audio.play("error")
        self.give_feedback(now, "MISSED", gfx.RED, "", 0.8)

    def draw_round(self, surf, now):
        cx, cy = self.CENTER
        # cockpit frame
        gfx.panel(surf, pygame.Rect(260, 120, 760, 470), (10, 16, 30), gfx.LINE, 24)
        for x in (300, 900):  # side gauges (static, low contrast so they don't distract)
            gfx.panel(surf, pygame.Rect(x, 170, 80, 340), (12, 20, 36), (28, 40, 66), 10)
            for k in range(6):
                pygame.draw.rect(surf, (28, 44, 70), (x + 16, 190 + k * 52, 48, 34), border_radius=4)
        active = self.state == "stim"
        gfx.alarm_light(surf, (cx, cy), 120, active)
        if active and self.onset is not None:
            ms = int((now - self.onset) * 1000)
            gfx.text(surf, f"{ms:03d}", (cx, cy), 56, (60, 10, 10), bold=True, mono=True, anchor="center")
        elif self.state == "feedback" and self.feedback:
            t, col, sub = self.feedback
            gfx.text(surf, t, (cx, cy - 6), 46, col, bold=True, mono=True, anchor="center")
            if sub:
                gfx.text(surf, sub.upper(), (cx, cy + 40), 18, col, bold=True, mono=True, anchor="center")
        # streak meter (rewards steadiness, not speed)
        gfx.text(surf, "STEADY STREAK", (cx, 560), 16, gfx.MUTED, mono=True, anchor="center")
        for k in range(10):
            col = gfx.GREEN if k < min(self.streak, 10) else gfx.LINE
            pygame.draw.rect(surf, col, (cx - 150 + k * 30, 578, 24, 8), border_radius=3)
        draw_footer(surf, "Press  SPACE  the instant the MASTER ALARM lights up.  Don't guess.   (ESC = pause)")


# =====================================================================
# ROUND 2 - DEBRIS WATCH  (go / no-go: decision + self-control)
# =====================================================================
class DebrisWatchRound(RoundScene):
    number = 2
    title = "DEBRIS WATCH"
    CENTER = (640, 380)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.laser_until = 0.0
        self.hide_object = False

    def window(self):
        return C.R2_WINDOW_S

    def isi_range(self):
        return C.R2_ISI_S

    def begin_trial(self, now):
        self.hide_object = False
        super().begin_trial(now)

    def on_key(self, key, now):
        if key != pygame.K_SPACE:
            return
        if self.state == "isi":
            self.record("false_start", False, None, "space", counts=False)
            self.app.audio.play("error")
            self.give_feedback(now, "WAIT FOR CONTACT", gfx.RED, "", 0.7, then="repeat")
        elif self.state == "stim":
            rt = self.rt_ms(now)
            self.laser_until = now + 0.15
            self.app.audio.play("laser")
            if rt < C.FALSE_START_MS:
                self.record("false_start", False, rt, "space")
                self.give_feedback(now, "TOO EARLY", gfx.RED, "", 0.7)
            elif self.trial["stimulus"] == "debris":
                self.record("hit", True, rt, "space")
                self.hide_object = True
                self.particles.burst(self.CENTER, (255, 140, 80), seed=self.trial["seed"])
                self.app.audio.play("boom")
                self.give_feedback(now, "DEBRIS CLEARED", gfx.GREEN, f"{rt:.0f} ms", C.R2_FEEDBACK_S)
            else:
                self.record("false_alarm", False, rt, "space")
                self.app.audio.play("error")
                self.give_feedback(now, "FRIENDLY FIRE!", gfx.RED, "that was a satellite - hold fire", 0.8)

    def on_timeout(self, now):
        if self.trial["stimulus"] == "debris":
            self.record("miss", False, None, "")
            self.app.audio.play("error")
            self.give_feedback(now, "DEBRIS MISSED", gfx.RED, "", 0.7)
        else:
            self.record("correct_rejection", True, None, "")
            self.app.audio.play("safe")
            self.give_feedback(now, "SATELLITE SAFE", gfx.GREEN, "good hold", C.R2_FEEDBACK_S)

    def draw_round(self, surf, now):
        cx, cy = self.CENTER
        gfx.radar(surf, (cx, cy), 230, now)
        show = self.state == "stim" or (self.state == "feedback" and not self.hide_object
                                         and self.trial["stimulus"] == "satellite")
        if show:
            if self.trial["stimulus"] == "debris":
                gfx.debris(surf, (cx, cy), 62, self.trial["seed"])
            else:
                gfx.satellite(surf, (cx, cy), 62)
        if now < self.laser_until:
            pygame.draw.line(surf, (255, 90, 90), (cx, C.HEIGHT - 60), (cx, cy), 6)
            pygame.draw.line(surf, (255, 220, 220), (cx, C.HEIGHT - 60), (cx, cy), 2)
        if self.state == "feedback" and self.feedback:
            t, col, sub = self.feedback
            gfx.text(surf, t, (cx, 150), 34, col, bold=True, mono=True, anchor="center")
            if sub:
                gfx.text(surf, sub, (cx, 182), 18, col, mono=True, anchor="center")
        # legend
        gfx.panel(surf, pygame.Rect(40, 250, 210, 260), (10, 16, 30), gfx.LINE, 12)
        gfx.debris(surf, (145, 320), 34, 7)
        gfx.text(surf, "DEBRIS = FIRE", (145, 370), 18, gfx.RED, bold=True, mono=True, anchor="center")
        gfx.satellite(surf, (145, 430), 30)
        gfx.text(surf, "SATELLITE = HOLD", (145, 480), 18, gfx.GREEN, bold=True, mono=True, anchor="center")
        draw_footer(surf, "SPACE = fire at DEBRIS.   Do NOT fire at friendly SATELLITES.   (ESC = pause)")


# =====================================================================
# ROUND 3 - MISSION CONTROL ORDERS  (task switching: adaptation)
# =====================================================================
class OrdersRound(RoundScene):
    number = 3
    title = "MISSION CONTROL ORDERS"
    CENTER = (640, 400)
    KEYS = {pygame.K_f: "left", pygame.K_j: "right"}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.flash = {"left": 0.0, "right": 0.0}
        self.drift = 0.0

    def window(self):
        return C.R3_WINDOW_S

    def isi_range(self):
        return C.R3_ISI_S

    def begin_trial(self, now):
        self.feedback = None
        t = self.trial
        if t["is_first"] or t["is_switch"]:
            self.app.audio.play("radio")
            self.set_state("banner", now, 2.0 if t["is_first"] else C.R3_NEW_ORDERS_S)
        else:
            self.set_state("isi", now, t["isi_s"])

    def restart_trial(self, now):
        # after an early press: don't replay the "new orders" banner
        self.feedback = None
        self.set_state("isi", now, self.trial["isi_s"])

    def on_key(self, key, now):
        side = self.KEYS.get(key)
        if side is None:
            return
        self.flash[side] = now + 0.18
        if self.state == "isi":
            self.record("false_start", False, None, side, counts=False)
            self.app.audio.play("error")
            self.give_feedback(now, "WAIT FOR THE TARGET", gfx.RED, "", 0.6, then="repeat")
        elif self.state == "stim":
            rt = self.rt_ms(now)
            t = self.trial
            if rt < C.FALSE_START_MS:
                self.record("false_start", False, rt, side)
                self.app.audio.play("error")
                self.give_feedback(now, "TOO EARLY", gfx.RED, "", 0.6)
            elif side == t["correct_key"]:
                self.record("correct", True, rt, side)
                self.drift = -1 if side == "left" else 1
                self.app.audio.play("thruster")
                self.give_feedback(now, "CORRECT", gfx.GREEN, f"{rt:.0f} ms", C.R3_FEEDBACK_S)
            else:
                resp = "wrong" if t["congruent"] else "old_rule"
                self.record(resp, False, rt, side)
                self.app.audio.play("error")
                self.give_feedback(now, "WRONG THRUSTER", gfx.RED,
                                   f"orders are {t['rule'].upper()}", 0.8)

    def on_timeout(self, now):
        self.record("miss", False, None, "")
        self.app.audio.play("error")
        self.give_feedback(now, "TOO SLOW", gfx.RED, "", 0.7)

    def update(self, now, dt):
        self.drift *= max(0.0, 1 - dt * 3)
        super().update(now, dt)

    # ---------------- drawing
    def _rule_banner(self, surf, rule, y, big=False):
        size = 40 if big else 30
        gfx.text(surf, f"ORDERS:  BY {rule.upper()}", (640, y), size, gfx.AMBER if big else gfx.TEXT,
                 bold=True, anchor="center")
        y2 = y + (60 if big else 46)
        if rule == "shape":
            left_draw = lambda c: pygame.draw.polygon(
                surf, gfx.WHITE, [(c[0], c[1] - 16), (c[0] + 16, c[1] + 12), (c[0] - 16, c[1] + 12)])
            right_draw = lambda c: pygame.draw.circle(surf, gfx.WHITE, c, 15)
            lt, rt = "TRIANGLE", "CIRCLE"
        else:
            left_draw = lambda c: pygame.draw.rect(surf, gfx.ORANGE, (c[0] - 16, c[1] - 16, 32, 32), border_radius=6)
            right_draw = lambda c: pygame.draw.rect(surf, gfx.BLUE, (c[0] - 16, c[1] - 16, 32, 32), border_radius=6)
            lt, rt = "ORANGE", "BLUE"
        gfx.key_cap(surf, C.R3_LEFT_KEY_NAME, (470, y2))
        left_draw((520, y2))
        gfx.text(surf, lt, (548, y2), 20, gfx.MUTED, bold=True, mono=True, anchor="midleft")
        gfx.key_cap(surf, C.R3_RIGHT_KEY_NAME, (700, y2))
        right_draw((750, y2))
        gfx.text(surf, rt, (778, y2), 20, gfx.MUTED, bold=True, mono=True, anchor="midleft")

    def draw_round(self, surf, now):
        t = self.trial
        cx, cy = self.CENTER
        if self.state == "banner":
            gfx.panel(surf, pygame.Rect(260, 200, 760, 300), (24, 18, 8), gfx.AMBER, 18, 2)
            label = "INITIAL ORDERS" if t["is_first"] else "NEW ORDERS FROM MISSION CONTROL"
            gfx.text(surf, label, (640, 245), 22, gfx.AMBER, bold=True, mono=True, anchor="center")
            self._rule_banner(surf, t["rule"], 320, big=True)
            draw_footer(surf, "Get ready...")
            return
        gfx.panel(surf, pygame.Rect(300, 80, 680, 110), (12, 18, 34), gfx.LINE, 14)
        self._rule_banner(surf, t["rule"], 110)
        # capsule + target area
        gfx.panel(surf, pygame.Rect(420, 220, 440, 360), (9, 14, 27), gfx.LINE, 18)
        if self.state == "stim":
            gfx.r3_object(surf, (cx, cy), t["shape"], t["color"], 90)
        elif self.state == "feedback" and self.feedback:
            txt, col, sub = self.feedback
            gfx.text(surf, txt, (cx, cy - 10), 38, col, bold=True, mono=True, anchor="center")
            if sub:
                gfx.text(surf, sub, (cx, cy + 30), 18, col, mono=True, anchor="center")
        else:
            gfx.text(surf, "+", (cx, cy), 40, gfx.DIM, mono=True, anchor="center")
        gfx.capsule(surf, (int(cx + self.drift * 30), 625), 0.8, thrust=0.6 if abs(self.drift) > .2 else 0)
        # thruster buttons
        for side, x, name in (("left", 250, C.R3_LEFT_KEY_NAME), ("right", 1030, C.R3_RIGHT_KEY_NAME)):
            lit = now < self.flash[side]
            r = pygame.Rect(0, 0, 150, 110)
            r.center = (x, 400)
            gfx.panel(surf, r, (40, 60, 100) if lit else (14, 22, 40), gfx.ACCENT if lit else gfx.LINE, 16, 2)
            gfx.text(surf, name, (x, 385), 40, gfx.TEXT, bold=True, mono=True, anchor="center")
            gfx.text(surf, f"{side.upper()} THRUSTER", (x, 425), 14, gfx.MUTED, mono=True, anchor="center")
        draw_footer(surf, f"Follow the CURRENT orders:  {C.R3_LEFT_KEY_NAME} = left   {C.R3_RIGHT_KEY_NAME} = right.   (ESC = pause)")


ROUND_CLASSES = {1: MasterAlarmRound, 2: DebrisWatchRound, 3: OrdersRound}
