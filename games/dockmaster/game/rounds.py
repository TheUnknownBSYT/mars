"""
The three DOCKMASTER tasks. Each has ONE simple rule:
  1 PORT SEQUENCE       click the docking ports in order 1, 2, 3, 4, 5
  2 TRACK THE SATELLITE follow the satellites that blinked, click them when they stop
  3 STEADY BEAM         keep the laser on the drifting satellite and count the GREEN flashes
"""
import math
from datetime import datetime

import pygame

import config as C
from core import generators as G
from game import gfx
from game.base import Scene, arena_bg, button, crosshair, dock_port, footer, header, satellite, side_panel


def stamp():
    return datetime.now().isoformat(timespec="milliseconds")


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TaskBase(Scene):
    number, title, rule = 0, "", ""

    def __init__(self, app, rounds, practice=False, on_done=None):
        super().__init__(app)
        self.rounds = rounds
        self.practice = practice
        self.on_done = on_done
        self.events = []
        self.i = 0
        self.state = None
        self.ts = 0.0
        self.started = False
        self.paused = False

    @property
    def rnd(self):
        return self.rounds[self.i]

    def set(self, s, now):
        self.state, self.ts = s, now

    def age(self, now):
        return now - self.ts

    def next_round(self, now):
        self.i += 1
        if self.i >= len(self.rounds):
            pygame.mouse.set_visible(True)
            if not self.practice and self.app.session:
                self.app.session.events[self.number] = self.events
            if self.on_done:
                self.on_done()
        else:
            self.begin(now)

    def handle(self, e, now):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.paused = not self.paused
            pygame.mouse.set_visible(True)
            if not self.paused:
                self.restart(now)
            return
        if self.paused:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_q:
                from game.screens import CheckinScene
                self.app.session = None
                self.app.go(CheckinScene(self.app))
            elif e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.paused = False
                self.restart(now)
            return
        if self.started and e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 1) == 1:
            self.on_click(e.pos, now)

    def update(self, now, dt):
        if not self.started:
            self.started = True
            self.begin(now)
            return
        if not self.paused:
            self.step(now, dt)

    def restart(self, now):
        self.events = [e for e in self.events if e.get("round") != self.rnd["round"]]
        self.begin(now)

    def draw(self, surf, now):
        surf.fill(gfx.BG)
        header(surf, self.app, f"TASK {self.number} · {self.title}",
               ("PRACTICE · not scored · " if self.practice else "") + f"ROUND {min(self.i + 1, len(self.rounds))}/{len(self.rounds)}")
        gfx.text(surf, self.rule, (C.WIDTH // 2, 82), 19, gfx.AMBER, bold=True, anchor="center")
        self.render(surf, now)
        if self.paused:
            veil = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
            veil.fill((4, 8, 16, 225))
            surf.blit(veil, (0, 0))
            gfx.text(surf, "SHIFT PAUSED", (C.WIDTH // 2, 300), 40, gfx.AMBER, bold=True, mono=True, anchor="center")
            gfx.text(surf, "ENTER resume (round restarts)    Q abort shift (nothing saved)", (C.WIDTH // 2, 352), 20, gfx.TEXT, anchor="center")

    def begin(self, now):
        pass

    def step(self, now, dt):
        pass

    def on_click(self, pos, now):
        pass

    def render(self, surf, now):
        pass


# =====================================================================
# TASK 1 - PORT SEQUENCE
# =====================================================================
class PortTask(TaskBase):
    number, title = 1, "PORT SEQUENCE"
    rule = "Click the docking ports in order: 1 → 2 → 3 → 4 → 5"

    def begin(self, now):
        pygame.mouse.set_visible(True)
        self.expected = 1
        self.used = {}            # port index -> number you assigned
        self.last_t = None
        self.first_ms = None
        self.ok = True
        self.set("show", now)

    def step(self, now, dt):
        if self.state == "show" and self.age(now) >= C.T1_SHOW_S:
            self.set("recall", now)
            self.last_t = now
        elif self.state == "recall" and self.age(now) >= C.T1_ROUND_TIMEOUT_S:
            self.end_round(now, timeout=True)
        elif self.state == "feedback" and self.age(now) >= C.T1_FEEDBACK_S:
            self.next_round(now)

    def on_click(self, pos, now):
        if self.state != "recall":
            return
        ports = self.rnd["ports"]
        free = [(dist(pos, p), k) for k, p in enumerate(ports) if k not in self.used]
        d, k = min(free) if free else (1e9, None)
        first = self.expected == 1 and not self.used
        dt_ms = (now - self.last_t) * 1000
        if first:
            self.first_ms = dt_ms
        if k is None or d > C.T1_PORT_RADIUS * 1.5:          # clicked empty space
            self.events.append({"task": 1, "kind": "click", "round": self.rnd["round"], "expected": self.expected, "clicked": 0,
                                "correct": 0, "first": int(first), "dt_ms": dt_ms, "err_px": None, "timestamp": stamp()})
            self.ok = False
            self.app.audio.play("error")
            self.last_t = now
            return
        number = k + 1
        correct = number == self.expected
        self.events.append({"task": 1, "kind": "click", "round": self.rnd["round"], "expected": self.expected, "clicked": number,
                            "correct": int(correct), "first": int(first), "dt_ms": dt_ms, "err_px": d, "timestamp": stamp()})
        self.used[k] = self.expected
        self.ok = self.ok and correct
        self.app.audio.play("tick" if correct else "error")
        self.expected += 1
        self.last_t = now
        if self.expected > C.T1_PORTS:
            self.end_round(now, timeout=False)

    def end_round(self, now, timeout):
        self.events.append({"task": 1, "kind": "round", "round": self.rnd["round"], "perfect": int(self.ok and not timeout),
                            "timeout": int(timeout), "first_click_ms": self.first_ms, "timestamp": stamp()})
        self.app.audio.play("chime" if self.ok and not timeout else "radio")
        self.set("feedback", now)

    def render(self, surf, now):
        arena_bg(surf)
        r = C.T1_PORT_RADIUS
        for k, p in enumerate(self.rnd["ports"]):
            n = k + 1
            if self.state == "show":
                dock_port(surf, p, r, gfx.ACCENT, (16, 34, 52))
                gfx.text(surf, str(n), p, 26, gfx.TEXT, bold=True, mono=True, anchor="center")
            elif self.state == "recall":
                hover = dist(self.app.mouse, p) <= r * 1.5 and k not in self.used
                dock_port(surf, p, r, gfx.ACCENT if hover else (120, 135, 170))
                if k in self.used:
                    gfx.text(surf, str(self.used[k]), p, 22, gfx.ACCENT, bold=True, mono=True, anchor="center")
            else:
                mine = self.used.get(k)
                col = gfx.GREEN if mine == n else (gfx.RED if mine else gfx.DIM)
                dock_port(surf, p, r, col)
                gfx.text(surf, str(n), p, 22, col, bold=True, mono=True, anchor="center")
        if self.state == "show":
            msg = f"MEMORISE · {max(0, C.T1_SHOW_S - self.age(now)):0.1f} s"
        elif self.state == "recall":
            msg = f"CLICK PORT {self.expected}"
        else:
            msg = "SEQUENCE CORRECT" if self.ok else "SEQUENCE ERROR"
        col = gfx.GREEN if self.state == "feedback" and self.ok else (gfx.RED if self.state == "feedback" else gfx.TEXT)
        gfx.text(surf, msg, (C.WIDTH // 2, C.ARENA[1] + C.ARENA[3] + 22), 20, col, bold=True, mono=True, anchor="center")
        side_panel(surf, pygame.Rect(20, 110, 195, 200), "HOW", ["Numbers show for 1.5 s, then hide.", "Click the ports in order from memory."], gfx.ACCENT)
        done = sum(1 for e in self.events if e["kind"] == "round")
        side_panel(surf, pygame.Rect(1065, 110, 195, 150), "LOG", [f"Round {min(self.i + 1, len(self.rounds))}/{len(self.rounds)}",
                                                                 f"Perfect {sum(e['perfect'] for e in self.events if e['kind'] == 'round')}/{done}"])
        footer(surf, "Mouse click · ESC pause")


# =====================================================================
# TASK 2 - TRACK THE SATELLITE
# =====================================================================
class TrackTask(TaskBase):
    number, title = 2, "TRACK THE SATELLITE"
    rule = "Follow the satellites that blink. Click them when they stop."

    def begin(self, now):
        pygame.mouse.set_visible(True)
        self.frames = G.track_frames(self.rnd)
        self.pos = self.frames[0]
        self.picks = []
        self.last_t = None
        self.set("blink", now)

    def step(self, now, dt):
        if self.state == "blink" and self.age(now) >= C.T2_BLINK_S:
            self.set("move", now)
        elif self.state == "move":
            k = min(len(self.frames) - 1, int(self.age(now) * 60))
            self.pos = self.frames[k]
            if self.age(now) >= C.T2_MOVE_S:
                self.pos = self.frames[-1]
                self.set("answer", now)
                self.last_t = now
        elif self.state == "answer" and self.age(now) >= C.T2_ANSWER_TIMEOUT_S:
            self.end_round(now, timeout=True)
        elif self.state == "feedback" and self.age(now) >= C.T2_FEEDBACK_S:
            self.next_round(now)

    def on_click(self, pos, now):
        if self.state != "answer":
            return
        cand = [(dist(pos, p), j) for j, p in enumerate(self.pos) if j not in self.picks]
        d, j = min(cand)
        if d > C.T2_RADIUS * 1.8:
            return                                   # empty space: ignore
        correct = j in self.rnd["tagged"]
        self.picks.append(j)
        self.events.append({"task": 2, "kind": "pick", "round": self.rnd["round"], "correct": int(correct),
                            "time_ms": (now - self.last_t) * 1000, "err_px": d, "timestamp": stamp()})
        self.last_t = now
        self.app.audio.play("tick")
        if len(self.picks) >= C.T2_TAGGED:
            self.end_round(now, timeout=False)

    def end_round(self, now, timeout):
        nc = sum(1 for j in self.picks if j in self.rnd["tagged"])
        self.events.append({"task": 2, "kind": "round", "round": self.rnd["round"], "n_correct": nc, "n_targets": C.T2_TAGGED,
                            "timeout": int(timeout), "timestamp": stamp()})
        self.app.audio.play("chime" if nc == C.T2_TAGGED else "radio")
        self.ok = nc
        self.set("feedback", now)

    def render(self, surf, now):
        arena_bg(surf)
        tagged = self.rnd["tagged"]
        for j, p in enumerate(self.pos):
            satellite(surf, p, C.T2_RADIUS)
            if self.state == "blink" and j in tagged and int(self.age(now) * 4) % 2 == 0:
                pygame.draw.circle(surf, gfx.AMBER, (int(p[0]), int(p[1])), C.T2_RADIUS + 14, 3)
            if self.state == "answer" and j not in self.picks and dist(self.app.mouse, p) <= C.T2_RADIUS * 1.8:
                pygame.draw.circle(surf, gfx.ACCENT, (int(p[0]), int(p[1])), C.T2_RADIUS + 12, 2)
            if j in self.picks:
                col = gfx.ACCENT if self.state == "answer" else (gfx.GREEN if j in tagged else gfx.RED)
                pygame.draw.circle(surf, col, (int(p[0]), int(p[1])), C.T2_RADIUS + 12, 3)
            if self.state == "feedback" and j in tagged and j not in self.picks:
                pygame.draw.circle(surf, gfx.AMBER, (int(p[0]), int(p[1])), C.T2_RADIUS + 12, 2)
        msgs = {"blink": "WATCH THE BLINKING SATELLITES", "move": "KEEP YOUR EYES ON THEM",
                "answer": f"CLICK THE {C.T2_TAGGED} SATELLITES · {len(self.picks)}/{C.T2_TAGGED}",
                "feedback": f"{getattr(self, 'ok', 0)}/{C.T2_TAGGED} CORRECT"}
        col = gfx.TEXT if self.state != "feedback" else (gfx.GREEN if getattr(self, "ok", 0) == C.T2_TAGGED else gfx.AMBER)
        gfx.text(surf, msgs.get(self.state, ""), (C.WIDTH // 2, C.ARENA[1] + C.ARENA[3] + 22), 20, col, bold=True, mono=True, anchor="center")
        side_panel(surf, pygame.Rect(20, 110, 195, 220), "HOW", ["Two satellites blink amber.", "They all move and mix.", "When they stop, click the two that blinked."], gfx.ACCENT)
        side_panel(surf, pygame.Rect(1065, 110, 195, 150), "LOG", [f"Round {min(self.i + 1, len(self.rounds))}/{len(self.rounds)}",
                                                                 f"Found {sum(e['correct'] for e in self.events if e['kind'] == 'pick')}"])
        footer(surf, "Follow with your eyes · click to select · ESC pause")


# =====================================================================
# TASK 3 - STEADY BEAM
# =====================================================================
class BeamTask(TaskBase):
    number, title = 3, "STEADY BEAM"
    rule = "Keep the laser on the satellite AND count the GREEN flashes."

    def begin(self, now):
        pygame.mouse.set_visible(True)
        self.err_sum = 0.0
        self.on_time = 0.0
        self.t_total = 0.0
        self.trail = []
        self.answer = None
        self.btns = []
        self.set("ready", now)

    def step(self, now, dt):
        if self.state == "ready" and self.age(now) >= 1.5:
            pygame.mouse.set_visible(False)
            self.set("track", now)
        elif self.state == "track":
            t = self.age(now)
            target = G.beam_position(self.rnd, t)
            d = dist(self.app.mouse, target)
            self.err_sum += d * dt
            self.t_total += dt
            if d <= C.T3_ON_TARGET_PX:
                self.on_time += dt
            if t >= C.T3_DURATION_S:
                pygame.mouse.set_visible(True)
                n = C.T3_ANSWER_MAX + 1
                w = 80
                x0 = C.WIDTH // 2 - (n * w + (n - 1) * 10) // 2
                self.btns = [(pygame.Rect(x0 + k * (w + 10), 420, w, 64), k) for k in range(n)]
                self.set("answer", now)
        elif self.state == "answer" and self.age(now) >= C.T3_ANSWER_TIMEOUT_S:
            self.finish_round(None, now)
        elif self.state == "feedback" and self.age(now) >= 1.6:
            self.next_round(now)

    def on_click(self, pos, now):
        if self.state != "answer":
            return
        for r, k in self.btns:
            if r.collidepoint(pos):
                self.finish_round(k, now)
                return

    def finish_round(self, ans, now):
        greens = self.rnd["greens"]
        err = abs((ans if ans is not None else -10) - greens) if ans is not None else greens
        self.answer = ans
        self.events.append({"task": 3, "kind": "beam", "round": self.rnd["round"],
                            "track_err_px": self.err_sum / max(self.t_total, 1e-6),
                            "on_target_pct": 100 * self.on_time / max(self.t_total, 1e-6),
                            "greens": greens, "answer": ans, "count_err": err, "answer_ms": (now - self.ts) * 1000, "timestamp": stamp()})
        self.app.audio.play("chime" if err == 0 else "radio")
        self.set("feedback", now)

    def render(self, surf, now):
        arena_bg(surf, grid=False)
        x, y, w, h = C.ARENA
        if self.state in ("ready", "track"):
            t = self.age(now) if self.state == "track" else 0.0
            target = G.beam_position(self.rnd, t)
            satellite(surf, target, 20)
            for ft, colr, pos in self.rnd["flashes"]:
                if self.state == "track" and ft <= t <= ft + C.T3_FLASH_S:
                    c = gfx.GREEN if colr == "green" else gfx.RED
                    gfx.glow_circle(surf, c, (int(pos[0]), int(pos[1])), 10, strength=120)
                    pygame.draw.circle(surf, c, (int(pos[0]), int(pos[1])), 10)
            if self.state == "track":
                m = self.app.mouse
                on = dist(m, target) <= C.T3_ON_TARGET_PX
                pygame.draw.line(surf, (255, 90, 90) if on else (90, 60, 70), (x + w // 2, y + h), m, 2)
                crosshair(surf, m, gfx.GREEN if on else gfx.ACCENT, 18)
                pct = 100 * self.on_time / max(self.t_total, 1e-6)
                gfx.text(surf, f"ON TARGET {pct:4.0f}%   ·   {max(0, C.T3_DURATION_S - t):4.1f} s", (C.WIDTH // 2, y + h + 22), 18,
                         gfx.GREEN if on else gfx.TEXT, bold=True, mono=True, anchor="center")
            else:
                gfx.text(surf, "GET READY · laser on the satellite · count GREEN flashes", (C.WIDTH // 2, y + h + 22), 18, gfx.TEXT, bold=True, mono=True, anchor="center")
        elif self.state == "answer":
            gfx.text(surf, "How many GREEN flashes did you see?", (C.WIDTH // 2, 360), 30, gfx.TEXT, bold=True, anchor="center")
            for r, k in self.btns:
                button(surf, r, str(k), r.collidepoint(self.app.mouse), 26)
            gfx.text(surf, f"{max(0, C.T3_ANSWER_TIMEOUT_S - self.age(now)):0.1f} s", (C.WIDTH // 2, 520), 16, gfx.AMBER, mono=True, anchor="center")
        else:
            g = self.rnd["greens"]
            ok = self.answer == g
            gfx.text(surf, f"{'CORRECT' if ok else 'NOT QUITE'} · there were {g} green flashes", (C.WIDTH // 2, 380), 26,
                     gfx.GREEN if ok else gfx.AMBER, bold=True, anchor="center")
            e = self.events[-1]
            gfx.text(surf, f"Laser on target {e['on_target_pct']:.0f}% of the time", (C.WIDTH // 2, 430), 20, gfx.TEXT, anchor="center")
        side_panel(surf, pygame.Rect(20, 110, 195, 230), "HOW", ["Move the mouse to keep the laser on the satellite.",
                                                                ("Count only GREEN flashes at the edges.", gfx.GREEN), ("Ignore red ones.", gfx.RED)], gfx.ACCENT)
        side_panel(surf, pygame.Rect(1065, 110, 195, 130), "LOG", [f"Round {min(self.i + 1, len(self.rounds))}/{len(self.rounds)}"])
        footer(surf, "Mouse = laser · ESC pause")


TASKS = {1: PortTask, 2: TrackTask, 3: BeamTask}
