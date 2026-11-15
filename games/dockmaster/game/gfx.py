"""
Drawing helpers: colours, fonts, text, and all the procedural space art
(no image files needed - everything is drawn with shapes).
"""
import math
import random

import pygame

import config as C

# ------------------------------------------------------------------ colours
BG = (6, 10, 20)
PANEL = (14, 22, 40)
PANEL2 = (20, 30, 54)
LINE = (38, 52, 86)
TEXT = (230, 236, 251)
MUTED = (138, 150, 182)
DIM = (86, 97, 127)
ACCENT = (79, 209, 255)
GREEN = (61, 220, 132)
AMBER = (255, 181, 71)
RED = (255, 93, 108)
ALARM = (255, 60, 50)
ORANGE = (255, 159, 28)
BLUE = (58, 134, 255)
VIOLET = (179, 155, 255)
WHITE = (255, 255, 255)

STATUS_COLOR = {"GO": GREEN, "CAUTION": AMBER, "NO-GO": RED, "RETEST": MUTED, "PRACTICE": ACCENT}
COMP_COLOR = {"normal": GREEN, "watch": AMBER, "slower": RED}
R3_COLORS = {"orange": ORANGE, "blue": BLUE}

# ------------------------------------------------------------------ fonts
_fonts = {}


def font(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _fonts:
        if mono:
            f = pygame.font.SysFont("consolas,menlo,dejavusansmono,couriernew,monospace", size, bold=bold)
        else:
            f = pygame.font.Font(None, int(size * 1.25))   # default font renders small; scale up
            f.set_bold(bold)
        _fonts[key] = f
    return _fonts[key]


def text(surf, s, pos, size=24, color=TEXT, bold=False, mono=False, anchor="topleft"):
    img = font(size, bold, mono).render(str(s), True, color)
    r = img.get_rect()
    setattr(r, anchor, pos)
    surf.blit(img, r)
    return r


def wrap(s, size, width, bold=False):
    f = font(size, bold)
    words, lines, cur = str(s).split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if f.size(test)[0] <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_block(surf, s, pos, width, size=22, color=TEXT, bold=False, spacing=6):
    x, y = pos
    for line in wrap(s, size, width, bold):
        r = text(surf, line, (x, y), size, color, bold)
        y = r.bottom + spacing
    return y


def panel(surf, rect, color=PANEL, border=LINE, radius=14, width=1):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, width, border_radius=radius)


def pill(surf, s, pos, color, size=18, anchor="topleft", filled=False):
    img = font(size, True, mono=True).render(s, True, BG if filled else color)
    r = img.get_rect().inflate(22, 12)
    setattr(r, anchor, pos)
    if filled:
        pygame.draw.rect(surf, color, r, border_radius=r.height // 2)
    else:
        pygame.draw.rect(surf, color, r, 2, border_radius=r.height // 2)
    surf.blit(img, img.get_rect(center=r.center))
    return r


def key_cap(surf, label, center, size=22, color=TEXT):
    img = font(size, True, mono=True).render(label, True, color)
    r = img.get_rect().inflate(18, 10)
    r.center = center
    pygame.draw.rect(surf, PANEL2, r, border_radius=6)
    pygame.draw.rect(surf, color, r, 2, border_radius=6)
    pygame.draw.line(surf, color, (r.left + 3, r.bottom), (r.right - 3, r.bottom), 3)
    surf.blit(img, img.get_rect(center=r.center))
    return r


def glow_circle(surf, color, center, radius, layers=5, strength=60):
    g = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
    c = radius * 2
    for i in range(layers, 0, -1):
        a = max(0, int(strength * (1 - i / (layers + 1))))
        pygame.draw.circle(g, (*color, a), (c, c), int(radius + i * radius * 0.18))
    surf.blit(g, (center[0] - c, center[1] - c))


# ------------------------------------------------------------------ background
class Starfield:
    def __init__(self, n=160, seed=4):
        rng = random.Random(seed)
        self.stars = [[rng.uniform(0, C.WIDTH), rng.uniform(0, C.HEIGHT),
                       rng.choice([0.2, 0.5, 1.0]), rng.choice([1, 1, 1, 2])] for _ in range(n)]

    def update(self, dt, speed=12):
        for s in self.stars:
            s[0] -= s[2] * speed * dt
            if s[0] < 0:
                s[0] += C.WIDTH

    def draw(self, surf):
        for x, y, depth, size in self.stars:
            v = int(90 + 165 * depth)
            pygame.draw.rect(surf, (v, v, min(255, v + 20)), (int(x), int(y), size, size))


_earth_cache = {}


def earth(surf, center, radius):
    """Planet Earth (cached image)."""
    if radius not in _earth_cache:
        size = radius * 2 + 40
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        for i in range(10, 0, -1):      # atmosphere glow
            pygame.draw.circle(img, (80, 170, 255, 10 + i * 2), (c, c), radius + i * 2)
        for i in range(radius, 0, -max(1, radius // 30)):   # ocean shading
            t = i / radius
            pygame.draw.circle(img, (int(20 + 30 * (1 - t)), int(70 + 60 * (1 - t)), int(150 + 70 * (1 - t))),
                               (c - int((1 - t) * radius * 0.25), c - int((1 - t) * radius * 0.25)), i)
        rng = random.Random(11)
        for _ in range(9):              # continents
            ang, dist = rng.uniform(0, math.tau), rng.uniform(0, radius * 0.7)
            cx, cy = c + math.cos(ang) * dist, c + math.sin(ang) * dist
            w, h = rng.uniform(radius * .2, radius * .5), rng.uniform(radius * .1, radius * .3)
            pygame.draw.ellipse(img, (60, 140, 80, 230), (cx - w / 2, cy - h / 2, w, h))
        for _ in range(7):              # clouds
            ang, dist = rng.uniform(0, math.tau), rng.uniform(0, radius * 0.8)
            cx, cy = c + math.cos(ang) * dist, c + math.sin(ang) * dist
            w = rng.uniform(radius * .3, radius * .6)
            pygame.draw.ellipse(img, (240, 245, 255, 90), (cx - w / 2, cy - 8, w, 16))
        mask = pygame.Surface((size, size), pygame.SRCALPHA)   # keep land/clouds inside the disc
        pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), radius + 20)
        img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        _earth_cache[radius] = img
    img = _earth_cache[radius]
    surf.blit(img, img.get_rect(center=center))


def station(surf, center, scale=1.0, modules=10):
    """Space station; `modules` = how many parts are unlocked (progression)."""
    x, y = center
    s = scale
    pygame.draw.line(surf, (150, 160, 185), (x - 150 * s, y), (x + 150 * s, y), max(2, int(5 * s)))  # truss
    parts = [
        lambda: pygame.draw.rect(surf, (200, 205, 220), (x - 30 * s, y - 18 * s, 60 * s, 36 * s), border_radius=int(8 * s)),
        lambda: [_panel(surf, (x + dx * s, y - 40 * s), s) for dx in (-140, -100)],
        lambda: pygame.draw.rect(surf, (185, 190, 210), (x + 30 * s, y - 14 * s, 50 * s, 28 * s), border_radius=int(6 * s)),
        lambda: pygame.draw.rect(surf, (120, 200, 140), (x - 80 * s, y - 14 * s, 50 * s, 28 * s), border_radius=int(6 * s)),
        lambda: pygame.draw.rect(surf, (170, 180, 230), (x - 18 * s, y + 18 * s, 36 * s, 40 * s), border_radius=int(6 * s)),
        lambda: pygame.draw.circle(surf, (140, 200, 255), (int(x), int(y - 26 * s)), int(12 * s)),
        lambda: pygame.draw.lines(surf, (230, 200, 90), False, [(x + 80 * s, y), (x + 110 * s, y - 40 * s), (x + 135 * s, y - 25 * s)], max(2, int(4 * s))),
        lambda: pygame.draw.rect(surf, (210, 210, 225), (x - 18 * s, y - 70 * s, 36 * s, 36 * s), border_radius=int(6 * s)),
        lambda: pygame.draw.line(surf, (220, 220, 235), (x + 55 * s, y - 14 * s), (x + 55 * s, y - 60 * s), max(1, int(3 * s))),
        lambda: [_panel(surf, (x + dx * s, y - 40 * s), s) for dx in (100, 140)],
    ]
    for p in parts[:max(1, modules)]:
        p()
    pygame.draw.circle(surf, ACCENT, (int(x + 90 * s), int(y)), max(3, int(7 * s)), 2)  # docking port


def _panel(surf, topleft, s):
    r = pygame.Rect(int(topleft[0]), int(topleft[1]), int(30 * s), int(80 * s))
    pygame.draw.rect(surf, (40, 80, 170), r)
    for k in range(1, 4):
        yy = r.top + k * r.height // 4
        pygame.draw.line(surf, (90, 140, 230), (r.left, yy), (r.right, yy), 1)
    pygame.draw.rect(surf, (120, 160, 240), r, 1)


def capsule(surf, center, scale=1.0, thrust=0.0, facing=1):
    """Crew capsule pointing right (facing=1) toward the station."""
    x, y = center
    s = scale * facing
    body = [(x - 40 * s, y - 22 * scale), (x + 25 * s, y - 12 * scale), (x + 25 * s, y + 12 * scale), (x - 40 * s, y + 22 * scale)]
    if thrust > 0:
        L = 20 + 30 * thrust
        pygame.draw.polygon(surf, ORANGE, [(x - 40 * s, y - 10 * scale), (x - (40 + L) * s, y), (x - 40 * s, y + 10 * scale)])
        pygame.draw.polygon(surf, (255, 230, 120), [(x - 40 * s, y - 5 * scale), (x - (40 + L * .6) * s, y), (x - 40 * s, y + 5 * scale)])
    pygame.draw.polygon(surf, (225, 230, 240), body)
    pygame.draw.polygon(surf, (150, 160, 185), body, 2)
    pygame.draw.rect(surf, (200, 205, 220), (min(x + 25 * s, x + 35 * s), y - 7 * scale, abs(10 * s), 14 * scale))
    pygame.draw.circle(surf, ACCENT, (int(x - 8 * s), int(y)), int(6 * scale))


# ------------------------------------------------------------------ round art
def alarm_light(surf, center, radius, active, label="MASTER ALARM", t=0.0):
    x, y = center
    if active:
        glow_circle(surf, ALARM, center, radius, strength=90)
        pygame.draw.circle(surf, (255, 90, 70), center, radius)
        pygame.draw.circle(surf, (255, 170, 140), center, int(radius * 0.72))
        pygame.draw.circle(surf, (255, 235, 220), center, int(radius * 0.3))
    else:
        pygame.draw.circle(surf, (40, 16, 22), center, radius)
        pygame.draw.circle(surf, (90, 30, 38), center, int(radius * 0.72))
    pygame.draw.circle(surf, (120, 130, 160), center, radius + 8, 4)
    text(surf, label, (x, y + radius + 26), 20, MUTED, bold=True, mono=True, anchor="center")


def radar(surf, center, radius, t):
    x, y = center
    pygame.draw.circle(surf, (8, 26, 22), center, radius)
    for k in (0.33, 0.66, 1.0):
        pygame.draw.circle(surf, (30, 90, 70), center, int(radius * k), 1)
    pygame.draw.line(surf, (30, 90, 70), (x - radius, y), (x + radius, y), 1)
    pygame.draw.line(surf, (30, 90, 70), (x, y - radius), (x, y + radius), 1)
    ang = (t * 1.6) % math.tau
    for k in range(14):  # fading sweep
        a = ang - k * 0.035
        col = (40, max(60, 200 - k * 12), max(50, 150 - k * 8))
        pygame.draw.line(surf, col, center, (x + math.cos(a) * radius, y + math.sin(a) * radius), 2)
    pygame.draw.circle(surf, (60, 160, 120), center, radius, 3)


def debris(surf, center, size, seed):
    rng = random.Random(seed)
    pts = []
    n = 9
    for i in range(n):
        a = i / n * math.tau
        r = size * rng.uniform(0.55, 1.0)
        pts.append((center[0] + math.cos(a) * r, center[1] + math.sin(a) * r))
    glow_circle(surf, (255, 80, 60), center, int(size * 0.8), strength=50)
    pygame.draw.polygon(surf, (200, 70, 50), pts)
    pygame.draw.polygon(surf, (255, 140, 90), pts, 3)
    for _ in range(3):
        a, r = rng.uniform(0, math.tau), rng.uniform(0, size * .4)
        pygame.draw.circle(surf, (120, 40, 30), (int(center[0] + math.cos(a) * r), int(center[1] + math.sin(a) * r)), int(size * .12))


def satellite(surf, center, size):
    x, y = center
    s = size
    glow_circle(surf, GREEN, center, int(s * 0.6), strength=40)
    pygame.draw.line(surf, (180, 230, 200), (x - s * 1.2, y), (x + s * 1.2, y), 3)
    for dx in (-1, 1):
        r = pygame.Rect(0, 0, int(s * .7), int(s * .9))
        r.center = (int(x + dx * s * .85), int(y))
        pygame.draw.rect(surf, (40, 150, 90), r)
        pygame.draw.rect(surf, (140, 240, 180), r, 2)
        pygame.draw.line(surf, (140, 240, 180), (r.centerx, r.top), (r.centerx, r.bottom), 1)
    body = pygame.Rect(0, 0, int(s * .55), int(s * .55))
    body.center = center
    pygame.draw.rect(surf, (90, 220, 140), body, border_radius=6)
    pygame.draw.line(surf, (200, 255, 220), (x, y - s * .28), (x, y - s * .7), 2)
    pygame.draw.circle(surf, (200, 255, 220), (int(x), int(y - s * .72)), 5)


def r3_object(surf, center, shape, color_name, size):
    col = R3_COLORS[color_name]
    glow_circle(surf, col, center, int(size * .7), strength=45)
    x, y = center
    if shape == "triangle":
        pts = [(x, y - size), (x + size * .95, y + size * .75), (x - size * .95, y + size * .75)]
        pygame.draw.polygon(surf, col, pts)
        pygame.draw.polygon(surf, WHITE, pts, 3)
    else:
        pygame.draw.circle(surf, col, center, int(size * .85))
        pygame.draw.circle(surf, WHITE, center, int(size * .85), 3)


class Particles:
    def __init__(self):
        self.p = []

    def burst(self, pos, color, n=28, speed=260, seed=None):
        rng = random.Random(seed)
        for _ in range(n):
            a, v = rng.uniform(0, math.tau), rng.uniform(speed * .3, speed)
            self.p.append([pos[0], pos[1], math.cos(a) * v, math.sin(a) * v, rng.uniform(.3, .7), color])

    def update(self, dt):
        for q in self.p:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[4] -= dt
        self.p = [q for q in self.p if q[4] > 0]

    def draw(self, surf):
        for x, y, _, _, life, col in self.p:
            pygame.draw.circle(surf, col, (int(x), int(y)), max(1, int(life * 6)))
