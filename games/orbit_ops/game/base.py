"""
Scene base class + the Session object that holds one daily mission check.
"""
import random
from datetime import datetime

import pygame

import config as C
from core import logger, schedule
from game import gfx


class Scene:
    """One screen of the game. main.py calls handle -> update -> draw every frame."""
    precise = False          # True = poll keyboard ~1000x/s (reaction-time rounds)

    def __init__(self, app):
        self.app = app
        self.redraw = True

    def handle(self, event, now):
        pass

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        pass

    def on_flip(self, t):
        """Called right after the frame is shown on screen (used to time stimulus onset)."""
        pass


class Session:
    """Everything about today's mission check."""
    STEPS = ["brief1", "round1", "rest1", "brief2", "round2", "rest2", "brief3", "round3",
             "mood", "dock", "debrief"]

    def __init__(self, crew, checkin, practice_mode=False):
        self.crew = crew
        self.checkin = checkin            # sleep_hours, fatigue, stress, mood_pre
        self.practice_mode = practice_mode
        self.history = logger.load_history(crew)
        self.index = logger.next_session_index(crew)
        self.first_time = (not practice_mode) and self.index == 1
        self.started = datetime.now()
        self.rng = random.Random()
        self.schedules = {
            1: schedule.build_round1(self.rng),
            2: schedule.build_round2(self.rng),
            3: schedule.build_round3(self.rng),
        }
        self.results = {1: [], 2: [], 3: []}
        self.practiced = set()
        self.mood_post = None
        self.total = sum(len(s) for s in self.schedules.values())
        self.done = 0
        self.step = -1

    @property
    def data_source(self):
        return "practice" if self.practice_mode else "prototype_gameplay"

    def progress(self):
        return min(1.0, self.done / max(1, self.total))

    def practice_schedule(self, rnd):
        n = C.PRACTICE_TRIALS[rnd]
        if rnd == 1:
            return schedule.build_round1(self.rng, n)
        if rnd == 2:
            return schedule.build_round2(self.rng, n, max(1, round(n * 0.6)))
        return schedule.build_round3(self.rng, n)


# ------------------------------------------------------------------ shared HUD
def draw_hud(surf, app, title, subtitle="", show_progress=True):
    """Top bar: game title, crew, round name and distance-to-station bar."""
    pygame.draw.rect(surf, (8, 13, 26), (0, 0, C.WIDTH, 64))
    pygame.draw.line(surf, gfx.LINE, (0, 64), (C.WIDTH, 64), 1)
    pygame.draw.circle(surf, gfx.ACCENT, (34, 32), 11, 3)
    pygame.draw.circle(surf, gfx.ACCENT, (40, 20), 4)
    gfx.text(surf, "ORBIT OPS", (56, 20), 22, gfx.TEXT, bold=True)
    gfx.text(surf, title, (210, 14), 24, gfx.TEXT, bold=True)
    if subtitle:
        gfx.text(surf, subtitle, (210, 38), 16, gfx.MUTED, mono=True)
    s = app.session
    right = f"CREW {app.crew}"
    if s:
        right += "   PRACTICE" if s.practice_mode else f"   SESSION {s.index}"
    right += "   [M] SOUND " + ("OFF" if app.audio.muted else "ON")
    gfx.text(surf, right, (C.WIDTH - 24, 22), 16, gfx.MUTED, mono=True, anchor="topright")
    if show_progress and s:
        x0, x1, y = 640, 1000, 50
        pygame.draw.line(surf, gfx.LINE, (x0, y), (x1, y), 4)
        p = s.progress()
        px = x0 + (x1 - x0) * p
        pygame.draw.line(surf, gfx.ACCENT, (x0, y), (px, y), 4)
        gfx.capsule(surf, (int(px), y), 0.32)
        pygame.draw.circle(surf, gfx.TEXT, (x1 + 10, y), 6, 2)
        km = (1 - p) * 12.0
        gfx.text(surf, f"GATEWAY {km:4.1f} km", (x1 + 22, y - 8), 14, gfx.MUTED, mono=True)


def draw_footer(surf, s):
    gfx.text(surf, s, (C.WIDTH // 2, C.HEIGHT - 22), 17, gfx.MUTED, anchor="center")
