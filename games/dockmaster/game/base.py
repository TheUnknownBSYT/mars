"""Scene base, today's Session, header/footer, small drawing helpers."""
import math
import random
from datetime import datetime

import pygame

import config as C
from core import generators as G, logger
from game import gfx

CONSOLE = (9, 14, 26)
TELE = (150, 165, 200)


class Scene:
    def __init__(self, app):
        self.app = app

    def handle(self, e, now):
        pass

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        pass


class Session:
    STEPS = ["brief1", "ports", "brief2", "track", "brief3", "beam", "debrief"]

    def __init__(self, crew, checkin, practice=False):
        self.crew, self.checkin, self.practice = crew, checkin, practice
        self.history = logger.load_history(crew)
        self.index = logger.next_index(crew)
        self.first_time = not practice and self.index == 1
        self.started = datetime.now()
        self.rng = random.Random()
        self.ports = G.port_rounds(self.rng)
        self.track = G.track_rounds(self.rng)
        self.beam = G.beam_rounds(self.rng)
        self.events = {1: [], 2: [], 3: []}
        self.practiced = set()
        self.step = -1

    @property
    def source(self):
        return "practice" if self.practice else "prototype_gameplay"


def header(surf, app, title, sub=""):
    pygame.draw.rect(surf, (8, 12, 22), (0, 0, C.WIDTH, 56))
    pygame.draw.line(surf, gfx.LINE, (0, 56), (C.WIDTH, 56), 1)
    gfx.text(surf, "DOCKMASTER", (24, 14), 20, gfx.ACCENT, bold=True, mono=True)
    gfx.text(surf, "hand-eye · memory · attention", (24, 38), 11, gfx.DIM, mono=True)
    gfx.text(surf, title, (260, 12), 22, gfx.TEXT, bold=True)
    if sub:
        gfx.text(surf, sub, (260, 36), 14, gfx.MUTED, mono=True)
    s = app.session
    right = f"CREW {app.crew}" + ((" · PRACTICE" if s.practice else f" · SHIFT {s.index}") if s else "")
    right += "   [M] AUDIO " + ("OFF" if app.audio.muted else "ON")
    gfx.text(surf, right, (C.WIDTH - 20, 20), 14, gfx.MUTED, mono=True, anchor="topright")


def footer(surf, s):
    gfx.text(surf, s, (C.WIDTH // 2, C.HEIGHT - 20), 15, gfx.MUTED, anchor="center")


def arena_bg(surf, grid=True):
    x, y, w, h = C.ARENA
    pygame.draw.rect(surf, (5, 9, 18), (x, y, w, h))
    if grid:
        for gx in range(x, x + w, 60):
            pygame.draw.line(surf, (14, 22, 38), (gx, y), (gx, y + h), 1)
        for gy in range(y, y + h, 60):
            pygame.draw.line(surf, (14, 22, 38), (x, gy), (x + w, gy), 1)
    pygame.draw.rect(surf, gfx.LINE, (x, y, w, h), 2)


def side_panel(surf, rect, title, lines, accent=gfx.MUTED):
    gfx.panel(surf, rect, CONSOLE, gfx.LINE, 12)
    gfx.text(surf, title, (rect.x + 14, rect.y + 12), 12, accent, bold=True, mono=True)
    y = rect.y + 38
    for ln in lines:
        txt, col = ln if isinstance(ln, tuple) else (ln, TELE)
        if txt:
            y = gfx.text_block(surf, txt, (rect.x + 14, y), rect.w - 28, 15, col, spacing=4) + 6


def dock_port(surf, pos, r, color=(120, 135, 170), fill=(18, 26, 44)):
    x, y = int(pos[0]), int(pos[1])
    pygame.draw.circle(surf, fill, (x, y), r)
    pygame.draw.circle(surf, color, (x, y), r, 3)
    pygame.draw.circle(surf, color, (x, y), int(r * 0.55), 1)
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        pygame.draw.line(surf, color, (x + math.cos(a) * r * 0.6, y + math.sin(a) * r * 0.6), (x + math.cos(a) * r, y + math.sin(a) * r), 2)


def satellite(surf, pos, r=22, body=(190, 198, 220), panel=(60, 110, 200)):
    x, y = int(pos[0]), int(pos[1])
    pygame.draw.line(surf, (160, 170, 195), (x - r * 1.5, y), (x + r * 1.5, y), 2)
    for dx in (-1, 1):
        rect = pygame.Rect(0, 0, int(r * 0.8), int(r * 1.1))
        rect.center = (int(x + dx * r * 1.05), y)
        pygame.draw.rect(surf, panel, rect)
        pygame.draw.rect(surf, (140, 175, 240), rect, 1)
    b = pygame.Rect(0, 0, int(r * 0.8), int(r * 0.8))
    b.center = (x, y)
    pygame.draw.rect(surf, body, b, border_radius=4)


def crosshair(surf, pos, color=gfx.ACCENT, s=16):
    x, y = int(pos[0]), int(pos[1])
    pygame.draw.circle(surf, color, (x, y), s, 2)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(surf, color, (x + dx * (s - 6), y + dy * (s - 6)), (x + dx * (s + 8), y + dy * (s + 8)), 2)
    pygame.draw.circle(surf, color, (x, y), 2)


def button(surf, rect, label, hover=False, size=18):
    gfx.panel(surf, rect, (30, 44, 74) if hover else gfx.PANEL2, gfx.ACCENT if hover else gfx.LINE, 10, 2)
    gfx.text(surf, label, rect.center, size, gfx.TEXT, bold=True, mono=True, anchor="center")
