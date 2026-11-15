"""
STARSIGHT - Vision Check (Python / pygame version of the web prototype).

Install once:   pip install pygame numpy
Run:            python starsight_app.py              (full screen)
                python starsight_app.py --windowed   (1280x800 window)

Files it creates next to this script:
  starsight_history.json   saved scans + screen calibration (per crew ID)
  starsight_scans.csv      every saved scan, same columns as the web version's CSV export

Rounds: 1 GHOST SIGNALS (faint vision)  ·  2 SHARP SHOOTER (near vision, Tumbling E at 40 cm)
Keys: SPACE / click = tap  ·  arrow keys (or WASD) = direction  ·  ESC = abort / quit  ·  M = mute
Needs starsight_core.py in the same folder.
"""

import argparse
import json
import math
import os
import random
import sys
from datetime import datetime

import numpy as np
import pygame

import starsight_core as core
from starsight_core import VCFG as C

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(HERE, "starsight_history.json")
CSV_FILE = os.path.join(HERE, "starsight_scans.csv")

# ----------------------------------------------------------------- colours
BG = (5, 7, 15); PANEL = (13, 20, 38); PANEL2 = (19, 29, 53); LINE = (36, 49, 90)
TEXT = (232, 237, 251); MUTED = (138, 150, 182); DIM = (86, 97, 127)
ACCENT = (79, 209, 255); GOLD = (255, 209, 102); GREEN = (61, 220, 132); AMBER = (255, 181, 71); RED = (255, 93, 108)
GREY = (128, 128, 128); BLACK = (0, 0, 0); ORANGE = (255, 123, 84)
STATUS_COL = {"GO": GREEN, "CHECK": AMBER, "GLASSES": AMBER, "SCAN NOW": RED, "RETEST": MUTED, "PRACTICE": ACCENT}
CARD_W, CARD_H = 85.6, 53.98
HEADER_H, PLAYBAR_H = 64, 64


class Abort(Exception):
    pass


class App:
    def __init__(self, windowed=False):
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 800)) if windowed else pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("STARSIGHT - Vision Check")
        self.w, self.h = self.screen.get_size()
        self.clock = pygame.time.Clock()
        f, m = "dejavusans,arial,helvetica", "dejavusansmono,consolas,menlo,couriernew"
        self.F_H1 = pygame.font.SysFont(f, 44, bold=True)
        self.F_H2 = pygame.font.SysFont(f, 30, bold=True)
        self.F_B = pygame.font.SysFont(f, 22)
        self.F_BB = pygame.font.SysFont(f, 22, bold=True)
        self.F_S = pygame.font.SysFont(f, 17)
        self.F_M = pygame.font.SysFont(m, 15, bold=True)
        self.F_ML = pygame.font.SysFont(m, 28, bold=True)
        self.F_MXL = pygame.font.SysFont(m, 40, bold=True)
        rnd = random.Random(7)
        self.stars = [(rnd.randrange(self.w), rnd.randrange(self.h), rnd.choice([1, 1, 2])) for _ in range(90)]
        self.store = self._load()
        self.muted = False
        self._init_sound()
        self.crew = "AST-01"
        self.ci = {"queasy": None, "glasses": None, "practice": False}
        self.progress = None          # 0..1 when a scan is running
        self.title, self.sub = "STARSIGHT", "daily vision check"
        self.mute_rect = pygame.Rect(0, 0, 0, 0)

    # ============================================================ storage
    def _load(self):
        try:
            with open(HISTORY_FILE) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            with open(HISTORY_FILE, "w") as fh:
                json.dump(self.store, fh, indent=1)
        except OSError:
            pass

    def hist(self, crew=None):
        return self.store.get("crew", {}).get(crew or self.crew, [])

    def set_hist(self, rows, crew=None):
        self.store.setdefault("crew", {})[crew or self.crew] = rows
        self._save()

    def append_csv(self, row):
        new = not os.path.exists(CSV_FILE)
        try:
            with open(CSV_FILE, "a", newline="") as fh:
                text = core.to_csv([row])
                fh.write(text if new else text.split("\n", 1)[1])
        except OSError:
            pass

    # ============================================================ sound
    def _init_sound(self):
        self.sounds = {}
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1)

            def tone(f0, f1, dur, vol=0.25):
                n = int(44100 * dur)
                t = np.arange(n) / 44100
                f = np.linspace(f0, f1, n)
                wave = np.sin(2 * np.pi * np.cumsum(f) / 44100) * np.exp(-4 * t / dur) * vol
                return (wave * 32767).astype(np.int16)

            def snd(*parts):
                return pygame.mixer.Sound(buffer=np.concatenate(parts).tobytes())
            self.sounds = {"lock": snd(tone(880, 880, .07), tone(1320, 1320, .09)), "miss": snd(tone(220, 160, .2, .2)),
                           "laser": snd(tone(1600, 300, .14, .15)),
                           "tap": snd(tone(1500, 900, .08, .2)), "chime": snd(tone(660, 660, .12), tone(990, 990, .2)),
                           "scan": snd(tone(200, 900, .5, .15))}
        except Exception:
            self.sounds = {}

    def sfx(self, name):
        if not self.muted and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass

    # ============================================================ drawing helpers
    def text(self, msg, pos, font=None, color=TEXT, anchor="topleft", surf=None, alpha=None):
        s = (font or self.F_B).render(str(msg), True, color)
        if alpha is not None:
            s.set_alpha(alpha)
        r = s.get_rect(**{anchor: pos})
        (surf or self.screen).blit(s, r)
        return r

    def wrap(self, msg, font, width):
        words, lines, cur = str(msg).split(" "), [], ""
        for wd in words:
            test = (cur + " " + wd).strip()
            if font.size(test)[0] > width and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def para(self, msg, pos, width, font=None, color=TEXT, gap=6, surf=None, center=False):
        font = font or self.F_B
        x, y = pos
        for line in self.wrap(msg, font, width):
            if center:
                self.text(line, (x, y), font, color, "midtop", surf)
            else:
                self.text(line, (x, y), font, color, surf=surf)
            y += font.get_linesize() + gap
        return y

    def panel(self, rect, surf=None, border=LINE, fill=PANEL, width=1, radius=16):
        surf = surf or self.screen
        pygame.draw.rect(surf, fill, rect, border_radius=radius)
        pygame.draw.rect(surf, border, rect, width, border_radius=radius)

    def button(self, label, center, color=ACCENT, fg=(3, 16, 28), enabled=True, w=None, font=None):
        font = font or self.F_BB
        tw = font.size(label)[0]
        r = pygame.Rect(0, 0, w or tw + 44, 52)
        r.center = center
        col = color if enabled else (60, 70, 95)
        pygame.draw.rect(self.screen, col, r, border_radius=12)
        self.text(label, r.center, font, fg if enabled else MUTED, "center")
        return r

    def chip(self, label, topleft, on=False, font=None):
        font = font or self.F_S
        r = pygame.Rect(topleft[0], topleft[1], max(40, font.size(label)[0] + 26), 36)
        pygame.draw.rect(self.screen, ACCENT if on else (10, 17, 32), r, border_radius=18)
        pygame.draw.rect(self.screen, ACCENT if on else LINE, r, 1, border_radius=18)
        self.text(label, r.center, font, (4, 17, 29) if on else TEXT, "center")
        return r

    def background(self):
        self.screen.fill(BG)
        for x, y, s in self.stars:
            pygame.draw.circle(self.screen, (200, 205, 220), (x, y), s)

    def header(self):
        pygame.draw.rect(self.screen, (7, 11, 24), (0, 0, self.w, HEADER_H))
        pygame.draw.line(self.screen, LINE, (0, HEADER_H - 1), (self.w, HEADER_H - 1))
        pygame.draw.ellipse(self.screen, ACCENT, (22, 24, 26, 16), 3)
        pygame.draw.circle(self.screen, GOLD, (35, 32), 4)
        self.text("STARSIGHT", (58, 20), self.F_BB)
        self.text(self.title, (210, 12), self.F_BB)
        self.text(self.sub, (210, 38), self.F_M, MUTED)
        x = self.w - 20
        self.mute_rect = pygame.Rect(0, 0, 110, 28)
        self.mute_rect.midright = (x, 32)
        pygame.draw.rect(self.screen, LINE, self.mute_rect, 1, border_radius=6)
        self.text("SOUND OFF" if self.muted else "SOUND ON", self.mute_rect.center, self.F_M, MUTED, "center")
        r = self.text("CREW " + self.crew, (self.mute_rect.left - 16, 32), self.F_M, MUTED, "midright")
        if self.progress is not None:
            pr = self.text(f"SCAN {round(self.progress * 100)}%", (r.left - 16, 32), self.F_M, MUTED, "midright")
            bar = pygame.Rect(pr.left - 210, 29, 200, 6)
            pygame.draw.rect(self.screen, LINE, bar, border_radius=3)
            pygame.draw.rect(self.screen, ACCENT, (bar.x, bar.y, int(bar.w * self.progress), bar.h), border_radius=3)

    def events(self):
        out = []
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_m and not getattr(self, "typing", False):
                    self.muted = not self.muted
                    continue
                out.append(("key", e.key, getattr(e, "unicode", "")))
            elif e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 1) == 1:
                if self.mute_rect.collidepoint(e.pos):
                    self.muted = not self.muted
                    continue
                out.append(("click", e.pos, None))
            elif e.type == pygame.MOUSEBUTTONUP:
                out.append(("up", e.pos, None))
            elif e.type == pygame.MOUSEMOTION:
                out.append(("motion", e.pos, None))
            elif e.type == pygame.MOUSEWHEEL:
                out.append(("wheel", e.y, None))
        return out

    def flip(self):
        pygame.display.flip()
        self.clock.tick(60)

    # ============================================================ geometry
    def d2p(self, deg):
        cal = self.store["calib"]
        return math.tan(math.radians(deg)) * cal["dist"] * cal["ppmm"]

    def fits(self, ppmm, dist):
        """Ghost Signals portholes sit 6 deg either side of centre and are 4 deg wide: they must fit on screen."""
        W, H = self.w, self.h - PLAYBAR_H
        d2p = lambda d: math.tan(math.radians(d)) * dist * ppmm
        return d2p(C["CS_SIDE_DEG"] + C["CS_PATCH_DEG"] / 2 + .5) < W / 2 - 10 and d2p(C["CS_PATCH_DEG"] / 2 + 2) < H / 2 - 40

    def e_pixels(self, logmar):
        """Tumbling-E size at 40 cm. Returns (stroke_px, logMAR actually drawn, at_screen_limit).
        An E is 5 strokes tall; at logMAR 0 (20/20) it spans 5 arcminutes."""
        ppmm = self.store["calib"]["ppmm"]
        arcmin = 5 * 10 ** logmar
        h_px = 2 * C["SS_DIST_MM"] * math.tan(math.radians(arcmin / 60) / 2) * ppmm
        stroke = max(1, int(round(h_px / 5)))
        shown_mm = 5 * stroke / ppmm
        shown = math.log10(math.degrees(2 * math.atan(shown_mm / (2 * C["SS_DIST_MM"]))) * 60 / 5)
        return stroke, round(shown, 3), stroke == 1 and h_px / 5 < 1.0

    def draw_e(self, center, stroke, direction, color=BLACK, surf=None):
        surf = surf or self.screen
        cells = [(0, r) for r in range(5)] + [(c, r) for r in (0, 2, 4) for c in range(1, 5)]   # arms point RIGHT
        rot = {"right": lambda c, r: (c, r), "left": lambda c, r: (4 - c, r),
               "down": lambda c, r: (r, c), "up": lambda c, r: (r, 4 - c)}[direction]
        x0, y0 = int(center[0] - 2.5 * stroke), int(center[1] - 2.5 * stroke)
        for c, r in cells:
            cc, rr = rot(c, r)
            pygame.draw.rect(self.screen if surf is None else surf, color, (x0 + cc * stroke, y0 + rr * stroke, stroke, stroke))

    def max_dist(self, ppmm):
        for d in range(700, 199, -50):
            if self.fits(ppmm, d):
                return d
        return None

    # ============================================================ HOME
    def home(self, message=("", TEXT)):
        typing, clear_armed = False, False
        while True:
            self.typing = typing
            self.background()
            self.title, self.sub, self.progress = "STARSIGHT", "daily vision check", None
            self.header()
            x0 = max(40, (self.w - 1150) // 2)
            self.text("Eyes on the stars, pilot.", (x0, 90), self.F_H1)
            self.para("Two quick vision games (~2.5 min) watch for SANS, the eye changes many astronauts get in space. "
                      "Each eye is compared with its own normal and with the other eye.", (x0, 148), 900, self.F_B, MUTED)
            left = pygame.Rect(x0, 222, 600, 420)
            right = pygame.Rect(x0 + 620, 222, 530, 420)
            self.panel(left, fill=PANEL2)
            # crew field
            self.text("CREW ID", (left.x + 20, left.y + 18), self.F_M, MUTED)
            field = pygame.Rect(left.x + 20, left.y + 42, 200, 40)
            pygame.draw.rect(self.screen, (10, 17, 32), field, border_radius=8)
            pygame.draw.rect(self.screen, ACCENT if typing else LINE, field, 2 if typing else 1, border_radius=8)
            self.text(self.crew + ("|" if typing and (pygame.time.get_ticks() // 500) % 2 else ""), (field.x + 10, field.centery), self.F_ML, TEXT, "midleft")
            # queasy chips
            self.text("FEELING QUEASY / SPACE-SICK NOW?  (0 = NOT AT ALL, 10 = VERY)", (left.x + 20, left.y + 100), self.F_M, MUTED)
            qchips, cx = [], left.x + 20
            for v in range(11):
                r = self.chip(str(v), (cx, left.y + 124), self.ci["queasy"] == v)
                qchips.append((r, v))
                cx = r.right + 6
            q = self.ci["queasy"]
            if q is not None:
                self.text("Feeling fine" if q == 0 else "A little off: OK to test" if q <= C["QUEASY_MAX"]
                          else "Too queasy: results will be greyed out (nausea skews vision tests)",
                          (left.x + 20, left.y + 166), self.F_S, AMBER if q > C["QUEASY_MAX"] else MUTED)
            # glasses
            self.text("WEARING YOUR USUAL GLASSES / LENSES?", (left.x + 20, left.y + 200), self.F_M, MUTED)
            g1 = self.chip("Yes / don't need them", (left.x + 20, left.y + 224), self.ci["glasses"] == "yes")
            g2 = self.chip("No", (g1.right + 8, left.y + 224), self.ci["glasses"] == "no")
            self.text("Use the same ones every day so scans are comparable.", (left.x + 20, left.y + 266), self.F_S, MUTED)
            # mode
            self.text("MODE", (left.x + 20, left.y + 300), self.F_M, MUTED)
            m1 = self.chip("MISSION (saved)", (left.x + 20, left.y + 324), not self.ci["practice"])
            m2 = self.chip("PRACTICE (not saved)", (m1.right + 8, left.y + 324), self.ci["practice"])
            cal = self.store.get("calib")
            self.text(f"Screen calibrated ({cal['ppmm']:.2f} px/mm, {cal['dist'] // 10} cm).  [R] = recalibrate" if cal
                      else "Screen not calibrated yet: you'll do it first (30 s).", (left.x + 20, left.y + 380), self.F_S, MUTED)
            # right column
            top = pygame.Rect(right.x, right.y, right.w, 170)
            self.panel(top, fill=PANEL2)
            self.text("TODAY'S SCAN", (top.x + 20, top.y + 16), self.F_M, MUTED)
            self.text("1  GHOST SIGNALS", (top.x + 20, top.y + 46), self.F_BB)
            self.text("how faint can you see?", (top.right - 20, top.y + 48), self.F_S, MUTED, "topright")
            self.text("2  SHARP SHOOTER", (top.x + 20, top.y + 86), self.F_BB)
            self.text("how small can you read up close?", (top.right - 20, top.y + 88), self.F_S, MUTED, "topright")
            self.text("Each game runs once per eye: right eye, then left.", (top.x + 20, top.y + 130), self.F_S, MUTED)
            rec = pygame.Rect(right.x, right.y + 186, right.w, 234)
            self.panel(rec, fill=PANEL2)
            h = self.hist()
            valid = sum(1 for r in h if int(r.get("valid", 0) or 0) == 1)
            base = core.vision_baseline(h)
            nsim = sum(1 for r in h if r.get("data_source") == "simulated")
            self.text("CREW RECORD", (rec.x + 20, rec.y + 16), self.F_M, MUTED)
            lines = [f"{len(h)} saved scans" + (f" ({nsim} simulated)" if nsim else ""),
                     f"Personal baseline: ACTIVE ({base['n']} valid scans)" if base else f"Personal baseline: forming ({valid}/{C['BASELINE_MIN']} valid scans)",
                     f"Last result: {h[-1].get('status')} ({str(h[-1].get('timestamp'))[:10]})" if h else "No scans yet"]
            for i, l in enumerate(lines):
                self.text(l, (rec.x + 20, rec.y + 44 + i * 30), self.F_B, GREEN if (i == 1 and base) else TEXT)
            b_hist = self.chip("Load demo history (simulated)", (rec.x + 20, rec.y + 150))
            b_clear = self.chip("Click again to delete" if clear_armed else "Clear history", (b_hist.right + 10, rec.y + 150))
            # bottom buttons
            by = left.bottom + 50
            b_start = self.button("Start vision scan  >", (x0 + 130, by))
            b_demo = self.button("Demo: simulated day-140 astronaut", (b_start.right + 210, by), GOLD, (40, 28, 0), font=self.F_S)
            self.text(message[0], (x0, by + 40), self.F_S, message[1])
            self.para("Screening and education demo, not a medical device and not validated. Screen tests can't diagnose SANS: "
                      "they flag when to get a real eye scan. Keys: SPACE, LEFT/RIGHT, ESC, M = mute.", (x0, self.h - 56), 1100, self.F_S, DIM, 2)
            self.flip()

            for kind, a, uni in self.events():
                if kind == "key" and typing:
                    if a in (pygame.K_RETURN, pygame.K_TAB, pygame.K_ESCAPE):
                        typing = False
                    elif a == pygame.K_BACKSPACE:
                        self.crew = self.crew[:-1]
                    elif uni and (uni.isalnum() or uni in "-_") and len(self.crew) < 12:
                        self.crew = (self.crew + uni).upper()
                    continue
                if kind == "key":
                    if a == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    if a == pygame.K_r and cal:
                        self.store.pop("calib", None)
                        self._save()
                    if a == pygame.K_RETURN:
                        kind, a = "click", b_start.center
                if kind != "click":
                    continue
                if not self.crew:
                    self.crew = "AST-01"
                typing = field.collidepoint(a)
                for r, v in qchips:
                    if r.collidepoint(a):
                        self.ci["queasy"] = v
                if g1.collidepoint(a):
                    self.ci["glasses"] = "yes"
                if g2.collidepoint(a):
                    self.ci["glasses"] = "no"
                if m1.collidepoint(a):
                    self.ci["practice"] = False
                if m2.collidepoint(a):
                    self.ci["practice"] = True
                if b_hist.collidepoint(a):
                    self.set_hist(core.make_demo_history(self.crew, quantize=(lambda lm: self.e_pixels(lm)[1:]) if self.store.get("calib") else None))
                    message = (f"Loaded 6 SIMULATED healthy scans for {self.crew}. Your personal baseline is now active.", ACCENT)
                if b_clear.collidepoint(a):
                    if clear_armed:
                        self.set_hist([])
                        clear_armed = False
                        message = (f"History cleared for {self.crew}.", ACCENT)
                    else:
                        clear_armed = True
                    continue
                clear_armed = False
                if b_demo.collidepoint(a):
                    return "demo"
                if b_start.collidepoint(a):
                    if self.ci["queasy"] is None or self.ci["glasses"] is None:
                        message = ("Please answer both questions first.", AMBER)
                    else:
                        return "start"

    # ============================================================ CALIBRATION
    def calibrate(self):
        card_w, dist, drag = 324.0, 500, False
        dists = [300, 400, 500, 600]
        while True:
            self.background()
            self.title, self.sub = "CALIBRATION", "make the screen know real sizes"
            self.header()
            cx = self.w // 2
            self.text("ONE-TIME SETUP · 30 SECONDS", (cx, 86), self.F_M, GOLD, "midtop")
            self.text("Teach the screen real sizes", (cx, 108), self.F_H1, TEXT, "midtop")
            self.text("Hold a bank or ID card flat against the screen. Drag the slider until the box matches the card exactly.",
                      (cx, 166), self.F_B, MUTED, "midtop")
            ch = card_w * CARD_H / CARD_W
            box = pygame.Rect(0, 0, int(card_w), int(ch))
            box.center = (cx, 210 + ch / 2 + 10)
            pygame.draw.rect(self.screen, (40, 36, 20), box, border_radius=12)
            pygame.draw.rect(self.screen, GOLD, box, 3, border_radius=12)
            self.text("CARD", box.center, self.F_M, GOLD, "center")
            ty = box.bottom + 40
            track = pygame.Rect(cx - 260, ty, 520, 8)
            pygame.draw.rect(self.screen, LINE, track, border_radius=4)
            kx = track.left + (card_w - 150) / 750 * track.w
            pygame.draw.circle(self.screen, ACCENT, (int(kx), track.centery), 14)
            self.text("How far will you sit? (eye to screen)", (cx, ty + 34), self.F_M, MUTED, "midtop")
            chips, x = [], cx - 260
            for d in dists:
                r = self.chip(f"{d // 10} cm" + (" (arm's length)" if d == 500 else ""), (x, ty + 60), d == dist)
                chips.append((r, d))
                x = r.right + 8
            ppmm = card_w / CARD_W
            ok, md = self.fits(ppmm, dist), self.max_dist(ppmm)
            msg = (f"Fits this screen at {dist // 10} cm" if ok else
                   f"Too big for this screen at {dist // 10} cm. Pick {md // 10} cm or closer." if md else
                   "This screen is too small. Use a laptop or tablet in landscape.")
            self.text(msg, (cx, ty + 112), self.F_B, GREEN if ok else AMBER if md else RED, "midtop")
            done = self.button("Done  >", (cx, ty + 180), enabled=ok)
            self.flip()
            for kind, a, _ in self.events():
                if kind == "key":
                    if a == pygame.K_ESCAPE:
                        raise Abort()
                    if a == pygame.K_LEFT:
                        card_w -= 2
                    if a == pygame.K_RIGHT:
                        card_w += 2
                    if a == pygame.K_RETURN and ok:
                        kind, a = "click", done.center
                if kind == "click":
                    if abs(a[1] - track.centery) < 24 and track.left - 20 <= a[0] <= track.right + 20:
                        drag = True
                    for r, d in chips:
                        if r.collidepoint(a):
                            dist = d
                    if done.collidepoint(a) and ok:
                        self.store["calib"] = {"ppmm": card_w / CARD_W, "dist": dist}
                        self._save()
                        return
                if kind == "up":
                    drag = False
                if (kind == "motion" or kind == "click") and drag:
                    card_w = 150 + max(0.0, min(1.0, (a[0] - track.left) / track.w)) * 750
            card_w = max(150.0, min(900.0, card_w))

    # ============================================================ BRIEFING / EYE PROMPT
    BRIEF = {
        1: ("ROUND 1 OF 2 · FAINT VISION", "GHOST SIGNALS",
            ["A signal (soft stripes) appears in the middle and slowly fades away. Press SPACE or click anywhere the moment it's gone (you'll see GOT IT).",
             "Then signals flash inside one of two portholes. Click the porthole they were in, or press LEFT / RIGHT.",
             "They get very faint on purpose, which is how we find your limit. Can't see it? Guess. That's normal.",
             "Keep looking at the centre dot. One eye at a time."],
            "Measures contrast sensitivity, how faint a pattern you can still see. In SANS (space eye syndrome) this may drop "
            "before normal eye-chart vision does. It's not on NASA's routine in-flight eye test list."),
        2: ("ROUND 2 OF 2 · NEAR VISION", "SHARP SHOOTER",
            ["Bring the screen closer: 40 cm, about the length from your elbow to your fingertips.",
             "An enemy E-ship appears in your scope. Which way are its three arms pointing?",
             "Fire with the arrow keys (or WASD), swipe, or click the arrow buttons: UP, DOWN, LEFT, RIGHT.",
             "Hit = the next target is smaller. Miss = bigger. Too tiny to tell? Guess! That's how we find your limit.",
             "Wear your usual reading glasses if you use them."],
            "Measures near vision, the smallest detail you can read at reading distance. In SANS the back of the eye flattens and "
            "close-up things blur (hyperopic shift), the most common SANS change. NASA flies 'space anticipation glasses' for it."),
    }

    def wait_continue(self, draw, label):
        while True:
            self.background()
            self.header()
            draw()
            b = self.button(label, (self.w // 2, self.h - 70))
            self.flip()
            for kind, a, _ in self.events():
                if kind == "key" and a == pygame.K_ESCAPE:
                    raise Abort()
                if (kind == "key" and a in (pygame.K_SPACE, pygame.K_RETURN)) or (kind == "click" and b.collidepoint(a)):
                    return

    def draw_art(self, kind, center):
        r = pygame.Rect(0, 0, 420, 150)
        r.center = center
        pygame.draw.rect(self.screen, GREY, r, border_radius=14)
        if kind == 1:
            for sx in (-1, 1):
                pygame.draw.circle(self.screen, (160, 160, 160), (r.centerx + sx * 100, r.centery - 6), 44, 2)
            for i in range(9):
                shade = 160 if i % 2 == 0 else 100
                fade = abs(i - 4) / 5
                col = tuple(int(128 + (shade - 128) * (1 - fade)) for _ in range(3))
                pygame.draw.rect(self.screen, col, (r.centerx + 100 - 31 + i * 7, r.centery - 40, 5, 68))
            pygame.draw.circle(self.screen, BLACK, (r.centerx, r.centery - 6), 5)
            self.text("CLICK -> RIGHT", (r.centerx + 100, r.bottom - 22), self.F_M, (30, 30, 30), "midtop")
        else:
            pygame.draw.rect(self.screen, (11, 19, 36), r, border_radius=14)
            pygame.draw.circle(self.screen, (245, 245, 245), (r.centerx - 70, r.centery - 8), 56)
            pygame.draw.circle(self.screen, GOLD, (r.centerx - 70, r.centery - 8), 56, 3)
            self.draw_e((r.centerx - 70, r.centery - 8), 9, "up")
            for d, (dx, dy) in {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.items():
                cx, cy = r.centerx + 110 + dx * 38, r.centery - 8 + dy * 38
                pygame.draw.rect(self.screen, ACCENT if d == "up" else PANEL2, (cx - 16, cy - 16, 32, 32), border_radius=8)
                self.text({"up": "^", "down": "v", "left": "<", "right": ">"}[d], (cx, cy), self.F_BB, (3, 16, 28) if d == "up" else TEXT, "center")
            self.text("ARMS POINT UP -> FIRE UP", (r.centerx, r.bottom - 22), self.F_M, GOLD, "midtop")

    def briefing(self, rnd):
        k, title, lines, why = self.BRIEF[rnd]
        self.title, self.sub = "MISSION BRIEFING", k

        def draw():
            cx = self.w // 2
            self.text(k, (cx, 84), self.F_M, GOLD, "midtop")
            self.text(title, (cx, 104), self.F_H1, ACCENT, "midtop")
            self.draw_art(rnd, (cx, 245))
            box_h = 26 + sum(len(self.wrap(l, self.F_B, 810)) * (self.F_B.get_linesize() + 4) + 10 for l in lines)
            box = pygame.Rect(cx - 440, 335, 880, box_h)
            self.panel(box, fill=PANEL2)
            y = box.y + 18
            for line in lines:
                pygame.draw.circle(self.screen, GOLD, (box.x + 26, y + 12), 5)
                y = self.para(line, (box.x + 44, y), 810, self.F_B, TEXT, 4) + 10
            self.para(why, (cx, box.bottom + 14), 760, self.F_S, MUTED, 3, center=True)
        self.wait_continue(draw, "Got it (SPACE)")

    def eye_prompt(self, rnd, eye):
        cover = "LEFT" if eye == "right" else "RIGHT"
        self.title, self.sub = ("GHOST SIGNALS" if rnd == 1 else "SHARP SHOOTER"), f"{eye.upper()} EYE"

        def draw():
            cx, cy = self.w // 2, 230
            pygame.draw.circle(self.screen, (27, 40, 70), (cx, cy), 80)
            pygame.draw.circle(self.screen, ACCENT, (cx, cy), 80, 3)
            for sx in (-1, 1):
                pygame.draw.circle(self.screen, TEXT, (cx + sx * 32, cy - 14), 9)
            pygame.draw.arc(self.screen, TEXT, (cx - 32, cy + 6, 64, 36), math.pi + 0.3, 2 * math.pi - 0.3, 4)
            hx = cx - 32 if cover == "LEFT" else cx + 32
            hand = pygame.Rect(0, 0, 76, 56)
            hand.center = (hx, cy - 14)
            pygame.draw.rect(self.screen, AMBER, hand, border_radius=24)
            self.text("COVER", hand.center, self.F_M, (58, 38, 0), "center")
            self.text(f"(your {cover.lower()} eye)", (cx, cy + 92), self.F_M, MUTED, "midtop")
            self.text(f"Testing your {eye.upper()} eye", (cx, 360), self.F_H1, TEXT, "midtop")
            dist = (f"Sit {self.store['calib']['dist'] // 10} cm from the screen, about an arm's length." if rnd == 1 else
                    "Bring the screen to 40 cm: elbow to fingertips. Wear your usual reading glasses if you use them.")
            self.para(f"Cover your {cover} eye with your palm (don't press on it). " + dist, (cx, 430), 820, self.F_B, TEXT, 4, center=True)
            self.text("Turn screen brightness up · same room light as usual · ESC aborts", (cx, 510), self.F_S, MUTED, "midtop")
        self.wait_continue(draw, "Ready (SPACE)")

    # ============================================================ PLAY
    def gabor(self, freq, contrast):
        """Stripes with soft edges (Gabor patch); random dithering lets an 8-bit screen show very faint contrast."""
        ppd = self.d2p(1)
        size = max(8, int(round(C["CS_PATCH_DEG"] * ppd)))
        xs = np.arange(size) - size / 2
        x, y = np.meshgrid(xs, xs, indexing="ij")            # pygame wants [x, y]
        env = np.exp(-(x ** 2 + y ** 2) / (2 * (C["CS_SIGMA_DEG"] * ppd) ** 2))
        lum = 128 + 127.5 * contrast * np.sin(2 * np.pi * freq * x / ppd) * env + np.random.uniform(-.5, .5, x.shape)
        lum = np.clip(np.round(lum), 0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(np.stack([lum] * 3, axis=-1))

    def play(self, rnd, eye):
        if rnd == 2:
            return self.play_sharp(eye)
        test = core.ContrastTest(eye)
        t0 = pygame.time.get_ticks() / 1000
        now = lambda: pygame.time.get_ticks() / 1000 - t0
        W, H = self.w, self.h - PLAYBAR_H
        fb, combo, patch, patch_key = None, 0, None, None
        stage = pygame.Rect(0, PLAYBAR_H, W, H)
        off, rr = self.d2p(C["CS_SIDE_DEG"]), self.d2p(C["CS_PATCH_DEG"] / 2)
        title = f"{'GHOST SIGNALS' if rnd == 1 else 'SHARP SHOOTER'} · {eye.upper()} EYE"
        self.abort_rect = pygame.Rect(W - 110, 14, 92, 36)
        while True:
            t = now()
            for kind, a, _ in self.events():
                if kind == "key" and a == pygame.K_ESCAPE:
                    raise Abort()
                key = None
                x = None
                if kind == "key":
                    key = {pygame.K_SPACE: "tap", pygame.K_LEFT: "left", pygame.K_f: "left", pygame.K_RIGHT: "right", pygame.K_j: "right"}.get(a)
                elif kind == "click" and a[1] > PLAYBAR_H:
                    key, x = ("tapL" if a[0] < W / 2 else "tapR"), a[0]
                elif kind == "click" and self.abort_rect.collidepoint(a):
                    raise Abort()
                if key is None:
                    continue
                if rnd == 1:
                    cur = test.current
                    if test.waiting_for_side():
                        if t - test.trial_start < 0.25:
                            continue
                        if x is not None and abs(x - W / 2) < off * 0.5:
                            fb = (t, "< TAP A PORTHOLE >", "left or right side of the screen", AMBER)
                            continue
                        side = "left" if key in ("left", "tapL") else "right" if key in ("right", "tapR") else None
                        if side is None:
                            continue
                        test.tap(t, side)
                        if cur.correct:
                            combo += 1
                            self.sfx("lock")
                            fb = (t, "WARM-UP OK" if cur.warmup else "SIGNAL LOCKED", f"COMBO x{combo}" if combo > 1 else "", GREEN)
                        else:
                            combo = 0
                            self.sfx("miss")
                            fb = (t, "NOISE X", "tough one: keep going", RED)
                    elif not test.in_gap and cur is not None and cur.kind == "fade" and key in ("tap", "tapL", "tapR"):
                        test.tap(t)
                        self.sfx("lock")
                        fb = (t, "GOT IT", f"it faded out at {cur.tapped * 100:.1f}% strength", GREEN)
            test.update(t)
            self.progress = (self.step + test.progress) / 4

            # ---- draw
            self.screen.fill(GREY)
            if rnd == 1:
                cx, cy = W // 2, PLAYBAR_H + H // 2
                st = test.stim(t)
                if st:
                    key = ("fade", round(st["contrast"] * 1e4)) if st["side"] == "center" else (st["freq"], st["contrast"], len(test.trials))
                    if key != patch_key:
                        patch, patch_key = self.gabor(st["freq"], st["contrast"]), key
                    px = cx + (-off if st["side"] == "left" else off if st["side"] == "right" else 0)
                    self.screen.blit(patch, patch.get_rect(center=(int(px), cy)))
                if test.current is not None and test.current.kind == "side":
                    for sx in (-1, 1):
                        pygame.draw.circle(self.screen, (162, 162, 162), (int(cx + sx * off), cy), int(rr), 2)
                    if test.waiting_for_side():
                        self.text("< LEFT", (cx - off, cy + rr + 14), self.F_M, (216, 216, 216), "midtop")
                        self.text("RIGHT >", (cx + off, cy + rr + 14), self.F_M, (216, 216, 216), "midtop")
                pygame.draw.circle(self.screen, BLACK, (cx, cy), 5)
            self.draw_feedback(fb, t, W)
            if False:
                alpha = int(255 * max(0, 1 - (t - fb[0]) / 0.75))
                self.text(fb[1], (W // 2, PLAYBAR_H + 24), self.F_ML, fb[3], "midtop", alpha=alpha)
                if fb[2]:
                    self.text(fb[2], (W // 2, PLAYBAR_H + 62), self.F_M, fb[3], "midtop", alpha=alpha)
            # top bar
            pygame.draw.rect(self.screen, (7, 11, 24), (0, 0, W, PLAYBAR_H))
            self.text(title, (18, PLAYBAR_H // 2), self.F_BB, TEXT, "midleft")
            self.text(test.status_text(), (W // 2, PLAYBAR_H // 2), self.F_M, GOLD, "center")
            self.abort_rect = pygame.Rect(W - 110, 14, 92, 36)
            pygame.draw.rect(self.screen, RED, self.abort_rect, 1, border_radius=8)
            self.text("Abort", self.abort_rect.center, self.F_S, RED, "center")
            bar = pygame.Rect(W - 300, 29, 170, 6)
            pygame.draw.rect(self.screen, LINE, bar, border_radius=3)
            pygame.draw.rect(self.screen, GOLD, (bar.x, bar.y, int(bar.w * test.progress), 6), border_radius=3)
            self.flip()
            if test.done:
                return test.results()

    def draw_feedback(self, fb, t, W):
        if fb and t - fb[0] < 0.75:
            alpha = int(255 * max(0, 1 - (t - fb[0]) / 0.75))
            self.text(fb[1], (W // 2, PLAYBAR_H + 24), self.F_ML, fb[3], "midtop", alpha=alpha)
            if fb[2]:
                self.text(fb[2], (W // 2, PLAYBAR_H + 62), self.F_M, fb[3], "midtop", alpha=alpha)

    def play_topbar(self, title, status, progress, W):
        pygame.draw.rect(self.screen, (7, 11, 24), (0, 0, W, PLAYBAR_H))
        self.text(title, (18, PLAYBAR_H // 2), self.F_BB, TEXT, "midleft")
        self.text(status, (W // 2, PLAYBAR_H // 2), self.F_M, GOLD, "center")
        self.abort_rect = pygame.Rect(W - 110, 14, 92, 36)
        pygame.draw.rect(self.screen, RED, self.abort_rect, 1, border_radius=8)
        self.text("Abort", self.abort_rect.center, self.F_S, RED, "center")
        bar = pygame.Rect(W - 300, 29, 170, 6)
        pygame.draw.rect(self.screen, LINE, bar, border_radius=3)
        pygame.draw.rect(self.screen, GOLD, (bar.x, bar.y, int(bar.w * progress), 6), border_radius=3)

    def play_sharp(self, eye):
        """SHARP SHOOTER: Tumbling E near-vision test with a target-scope theme."""
        quant = lambda lm: self.e_pixels(lm)[1:]
        test = core.SharpTest(eye, quant)
        t0 = pygame.time.get_ticks() / 1000
        now = lambda: pygame.time.get_ticks() / 1000 - t0
        W, H = self.w, self.h - PLAYBAR_H
        cx, cy = W // 2, PLAYBAR_H + H // 2 - 10
        self.abort_rect = pygame.Rect(W - 110, 14, 92, 36)
        fb, hits, down_pos = None, 0, None
        keymap = {pygame.K_UP: "up", pygame.K_w: "up", pygame.K_DOWN: "down", pygame.K_s: "down",
                  pygame.K_LEFT: "left", pygame.K_a: "left", pygame.K_RIGHT: "right", pygame.K_d: "right"}
        rng = random.Random(3)
        stars = [(rng.randrange(W), rng.randrange(PLAYBAR_H, self.h), rng.choice([1, 1, 2])) for _ in range(120)]
        while True:
            t = now()
            scope_r = 150
            btns = {d: pygame.Rect(0, 0, 64, 64) for d in core.DIRS}
            btns["up"].center, btns["down"].center = (cx, cy - scope_r - 52), (cx, cy + scope_r + 52)
            btns["left"].center, btns["right"].center = (cx - scope_r - 52, cy), (cx + scope_r + 52, cy)
            for kind, a, _ in self.events():
                d = None
                if kind == "key":
                    if a == pygame.K_ESCAPE:
                        raise Abort()
                    d = keymap.get(a)
                elif kind == "click":
                    if self.abort_rect.collidepoint(a):
                        raise Abort()
                    d = next((k for k, r in btns.items() if r.collidepoint(a)), None)
                    if d is None:
                        down_pos = a
                elif kind == "up" and down_pos is not None:
                    dx, dy = a[0] - down_pos[0], a[1] - down_pos[1]
                    if max(abs(dx), abs(dy)) > 40:
                        d = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")
                    down_pos = None
                tgt = test.target()
                if d and tgt is not None and t - test.trial_start > 0.2:
                    test.tap(t, d)
                    self.sfx("laser")
                    if tgt.correct:
                        hits += 1
                        self.sfx("lock")
                        combo = test.combo + 1
                        fb = (t, "TARGET LOCKED" if not tgt.warmup else "WARM-UP HIT", f"COMBO x{combo}" if combo > 1 else "", GREEN)
                    else:
                        self.sfx("miss")
                        fb = (t, "MISSED", f"its arms pointed {tgt.direction.upper()}" if tgt.warmup else "tiny ones are tough: keep going", RED)
            test.update(t)
            self.progress = (self.step + test.progress) / 4

            self.screen.fill((5, 8, 18))
            for x, y, s2 in stars:
                pygame.draw.circle(self.screen, (120, 130, 160), (x, y), s2)
            pygame.draw.circle(self.screen, (245, 245, 245), (cx, cy), scope_r)
            ring = GOLD if test.target() is not None else LINE
            pygame.draw.circle(self.screen, ring, (cx, cy), scope_r, 4)
            for ang in range(0, 360, 90):
                a1 = math.radians(ang)
                pygame.draw.line(self.screen, (170, 170, 170), (cx + math.cos(a1) * (scope_r - 26), cy + math.sin(a1) * (scope_r - 26)),
                                 (cx + math.cos(a1) * (scope_r - 6), cy + math.sin(a1) * (scope_r - 6)), 3)
            tgt = test.target()
            if tgt is not None:
                stroke = self.e_pixels(tgt.level)[0]
                self.draw_e((cx, cy), stroke, tgt.direction)
            for d, r in btns.items():
                pygame.draw.rect(self.screen, PANEL2, r, border_radius=14)
                pygame.draw.rect(self.screen, LINE, r, 2, border_radius=14)
                self.text({"up": "^", "down": "v", "left": "<", "right": ">"}[d], r.center, self.F_H2, TEXT, "center")
            self.text(f"TARGETS LOCKED  {hits}", (30, PLAYBAR_H + 24), self.F_M, GREEN)
            self.text(f"COMBO x{test.combo}" if test.combo > 1 else "", (30, PLAYBAR_H + 50), self.F_M, GOLD)
            self.text("40 cm from the screen · arrow keys / WASD / swipe / buttons", (cx, self.h - 34), self.F_M, MUTED, "midtop")
            self.draw_feedback(fb, t, W)
            self.play_topbar(f"SHARP SHOOTER · {eye.upper()} EYE", test.status_text(), test.progress, W)
            self.flip()
            if test.done:
                return test.results()

    # ============================================================ REVEAL
    def reveal(self, rnd, eye, r):
        self.sfx("chime")
        self.title, self.sub = ("GHOST SIGNALS" if rnd == 1 else "SHARP SHOOTER"), f"{eye.upper()} EYE COMPLETE"

        def draw():
            cx = self.w // 2
            if rnd == 1:
                self.text(f"{eye.upper()} EYE: SIGNALS DECODED", (cx, 110), self.F_H2, GOLD, "midtop")
                cards = [(f"{l.upper()} SIGNALS", "-" if r.get("cs_" + l) is None else f"{10 ** -r['cs_' + l] * 100:.1f}%",
                          "faintest you could still see", TEXT) for l, _ in C["CS_FREQS"]]
                cards.append(("FAINT-VISION SCORE", str(r.get("cs_mean", "-")), "logCS · higher = sharper at faint", ACCENT))
                x = cx - (len(cards) * 250 + (len(cards) - 1) * 16) // 2
                for lab, val, small, col in cards:
                    rc = pygame.Rect(x, 190, 250, 140)
                    self.panel(rc)
                    self.text(lab, (rc.x + 18, rc.y + 16), self.F_M, MUTED)
                    self.text(val, (rc.x + 18, rc.y + 44), self.F_MXL, col)
                    self.text(small, (rc.x + 18, rc.y + 104), self.F_S, MUTED)
                    x += 266
                if r.get("cs_quality") != "ok":
                    self.text("! " + r.get("cs_reason", ""), (cx, 360), self.F_BB, AMBER, "midtop")
            else:
                self.text(f"{eye.upper()} EYE: SHARPEST TARGET", (cx, 100), self.F_H2, GOLD, "midtop")
                card = pygame.Rect(cx - 150, 150, 300, 200)
                pygame.draw.rect(self.screen, (245, 245, 245), card, border_radius=16)
                pygame.draw.rect(self.screen, GOLD, card, 3, border_radius=16)
                best = r.get("na_best")
                if best is not None:
                    stroke = self.e_pixels(best)[0]
                    self.draw_e(card.center, stroke, "right")
                    self.text("smallest E you locked (real size at 40 cm)", (cx, card.bottom - 26), self.F_M, (90, 90, 90), "midtop")
                lm = r.get("na_logmar")
                self.text(f"Near-vision score: {lm} logMAR  ≈ {core.snellen(lm)} at reading distance" if lm is not None else "No score",
                          (cx, 380), self.F_B, TEXT, "midtop")
                self.text("logMAR: 0.0 = normal 20/20 · lower = sharper · each 0.1 = one eye-chart line", (cx, 418), self.F_S, MUTED, "midtop")
                if r.get("na_floor"):
                    self.text("You hit this screen's smallest letter: your real near vision may be even sharper.", (cx, 452), self.F_S, ACCENT, "midtop")
                if r.get("na_quality") != "ok":
                    self.text("! " + r.get("na_reason", ""), (cx, 486), self.F_BB, AMBER, "midtop")
        self.wait_continue(draw, "Continue (SPACE)")

    # ============================================================ SESSION
    def run_scan(self):
        if not self.store.get("calib") or not self.fits(self.store["calib"]["ppmm"], self.store["calib"]["dist"]):
            self.calibrate()
        started, res = datetime.now(), {}
        self.step, self.progress = 0, 0.0
        for rnd in (1, 2):
            self.briefing(rnd)
            for eye in ("right", "left"):
                self.eye_prompt(rnd, eye)
                r = self.play(rnd, eye)
                res[(rnd, eye)] = r
                self.reveal(rnd, eye, r)
                self.step += 1
        self.progress = None
        R = {**res[(1, "right")], **res[(2, "right")]}
        L = {**res[(1, "left")], **res[(2, "left")]}
        return self.finish(R, L, "practice" if self.ci["practice"] else "prototype_gameplay", started)

    def run_demo(self):

        q = (lambda lm: self.e_pixels(lm)[1:]) if self.store.get("calib") else None
        if core.vision_baseline(self.hist()) is None:
            self.set_hist(self.hist() + core.make_demo_history(self.crew, quantize=q))
        R = core.simulate_eye("right", core.SimViewer(core.DEMO_RIGHT["cs"], core.DEMO_RIGHT["na"]), q)
        L = core.simulate_eye("left", core.SimViewer(), q)
        return self.finish(R, L, "simulated", datetime.now(), queasy=0, glasses="yes",
                           note="SIMULATED day-140 astronaut: SANS-like change in the right eye. Nobody played this session.")

    def finish(self, R, L, source, started, queasy=None, glasses=None, note=None):
        h = self.hist()
        row = core.build_row(R, L, {"crew": self.crew, "session": len(h) + 1, "timestamp": started.isoformat(timespec="seconds"),
                                    "data_source": source, "version": C["VERSION"],
                                    "queasy": self.ci["queasy"] if queasy is None else queasy,
                                    "glasses": self.ci["glasses"] if glasses is None else glasses})
        ev = core.evaluate_vision(row, h)
        row["status"] = "PRACTICE" if source == "practice" else ev["status"]
        if source != "practice":
            self.set_hist(h + [row])
            self.append_csv(row)
        self.debrief(row, ev, R, L, note)

    # ============================================================ DEBRIEF
    def debrief(self, row, ev, R, L, note):
        self.sfx("scan")
        content_h = 1240
        scroll = 0
        page = pygame.Surface((self.w, content_h))
        self._draw_debrief(page, row, ev, R, L, note)
        self.title, self.sub = "MISSION DEBRIEF", f"{row['crew']} · scan {row['session']}" + (" · PRACTICE (not saved)" if row["status"] == "PRACTICE" else "")
        view_h = self.h - HEADER_H
        while True:
            self.screen.fill(BG)
            self.screen.blit(page, (0, HEADER_H - scroll))
            self.header()
            b = self.button("New scan (ENTER)", (self.w - 130, HEADER_H + 36), w=220)
            if content_h > view_h:
                self.text("scroll for more (wheel / UP / DOWN)", (self.w - 20, self.h - 10), self.F_M, DIM, "bottomright")
            self.flip()
            for kind, a, _ in self.events():
                if kind == "wheel":
                    scroll -= a * 60
                if kind == "key":
                    if a == pygame.K_DOWN:
                        scroll += 60
                    if a == pygame.K_UP:
                        scroll -= 60
                    if a in (pygame.K_RETURN, pygame.K_ESCAPE):
                        return
                if kind == "click" and b.collidepoint(a):
                    return
            scroll = max(0, min(scroll, max(0, content_h - view_h)))

    def _draw_debrief(self, s, row, ev, R, L, note):
        s.fill(BG)
        x0 = max(30, (self.w - 1150) // 2)
        W = min(1150, self.w - 60)
        y = 20
        self.text("VISION DEBRIEF", (x0, y + 8), self.F_M, MUTED, surf=s)
        y += 60
        if note:
            r = pygame.Rect(x0, y, W, 44)
            pygame.draw.rect(s, GOLD, r, 1, border_radius=10)
            self.text(note, (r.x + 16, r.centery), self.F_BB, GOLD, "midleft", s)
            y += 60
        col = STATUS_COL.get(row["status"], MUTED)
        flag_lines = ([f"RIGHT eye: {f}" for f in ev["flags"]["R"]] + [f"LEFT eye: {f}" for f in ev["flags"]["L"]]) if row["valid"] else []
        msg_h = len(self.wrap(ev["message"], self.F_S, W - 140)) * (self.F_S.get_linesize() + 2)
        sh = 100 + msg_h + 26 * (len(flag_lines) + len(ev["notes"])) + 48
        sr = pygame.Rect(x0, y, W, sh)
        self.panel(sr, s, col, PANEL2, 2)
        pygame.draw.circle(s, col, (sr.x + 56, sr.y + 56), 34)
        self.text(row["status"], (sr.x + 110, sr.y + 16), self.F_H1, col, surf=s)
        self.text(ev["headline"], (sr.x + 110, sr.y + 70), self.F_BB, TEXT, surf=s)
        yy = self.para(ev["message"], (sr.x + 110, sr.y + 100), W - 140, self.F_S, TEXT, 2, s)
        for f in flag_lines:
            self.text("> " + f, (sr.x + 110, yy), self.F_S, AMBER, surf=s)
            yy += 26
        for n in ev["notes"]:
            self.text("- " + n, (sr.x + 110, yy), self.F_S, MUTED, surf=s)
            yy += 26
        conf_col = {"HIGH": GREEN, "MEDIUM": AMBER, "LOW": RED}[ev["confidence"]]
        self.text(f"CONFIDENCE {ev['confidence']}", (sr.x + 110, sr.bottom - 30), self.F_M, conf_col, surf=s)
        self.text(ev["why"], (sr.x + 290, sr.bottom - 30), self.F_S, MUTED, surf=s)
        y = sr.bottom + 18
        # eye cards
        cw = (W - 18) // 2
        for i, (name, r, e) in enumerate((("RIGHT", R, "R"), ("LEFT", L, "L"))):
            rc = pygame.Rect(x0 + i * (cw + 18), y, cw, 440)
            self.panel(rc, s)
            bad = not row["valid"]
            flagged = (not bad) and bool(ev["flags"][e])
            c = MUTED if bad else RED if flagged else GREEN
            self.text(f"{name} EYE", (rc.x + 18, rc.y + 16), self.F_M, MUTED, surf=s)
            pill = "UNRELIABLE" if bad else "CHANGED" if flagged else "NORMAL"
            pr = self.text(pill, (rc.right - 28, rc.y + 16), self.F_M, c, "topright", s)
            pygame.draw.rect(s, c, pr.inflate(18, 10), 2, border_radius=12)
            self.text("GHOST SIGNALS · faint vision (logCS)", (rc.x + 18, rc.y + 50), self.F_M, ACCENT, surf=s)
            pos = lambda v: max(0.0, min(1.0, (v - 0.8) / 1.4))
            for j, (l, _) in enumerate(C["CS_FREQS"]):
                by = rc.y + 82 + j * 32
                self.text(l, (rc.x + 18, by - 4), self.F_S, MUTED, surf=s)
                bar = pygame.Rect(rc.x + 80, by, cw - 160, 12)
                pygame.draw.rect(s, LINE, bar, border_radius=6)
                v = r.get("cs_" + l)
                if v is not None:
                    pygame.draw.rect(s, c, (bar.x, bar.y, int(bar.w * pos(v)), bar.h), border_radius=6)
                tx = bar.x + int(bar.w * pos(C["CS_TYPICAL"][l]))
                pygame.draw.rect(s, TEXT, (tx - 1, bar.y - 4, 3, 20))
                self.text("-" if v is None else f"{v:.2f}", (rc.right - 18, by - 4), self.F_M, TEXT, "topright", s)
            base = ev["base"]
            note2 = (f"white tick = rough typical · your normal {base['cs_mean_' + e]:.2f}, today {r.get('cs_mean')}"
                     if base and base.get("cs_mean_" + e) else f"white tick = rough typical · mean {r.get('cs_mean')}")
            self.text(note2, (rc.x + 18, rc.y + 150), self.F_M, MUTED, surf=s)
            self.text("SHARP SHOOTER · near vision at 40 cm (logMAR, lower = sharper)", (rc.x + 18, rc.y + 186), self.F_M, ACCENT, surf=s)
            lm = r.get("na_logmar")
            bar = pygame.Rect(rc.x + 18, rc.y + 240, cw - 36, 14)
            pygame.draw.rect(s, LINE, bar, border_radius=7)
            lo, hi = 1.0, -0.3                       # left = blurry, right = sharp
            px = lambda v: bar.x + int(bar.w * max(0.0, min(1.0, (lo - v) / (lo - hi))))
            if lm is not None:
                pygame.draw.rect(s, c, (bar.x, bar.y, px(lm) - bar.x, bar.h), border_radius=7)
            pygame.draw.rect(s, TEXT, (px(C["SS_TYPICAL"]) - 1, bar.y - 5, 3, 24))
            self.text("blurry", (bar.x, bar.bottom + 10), self.F_M, DIM, surf=s)
            self.text("sharp", (bar.right, bar.bottom + 10), self.F_M, DIM, "topright", s)
            self.text("20/20", (px(0), bar.y - 26), self.F_M, TEXT, "midtop", s)
            if base and base.get("na_logmar_" + e) is not None:
                bx = px(base["na_logmar_" + e])
                pygame.draw.polygon(s, ACCENT, [(bx, bar.bottom + 4), (bx - 7, bar.bottom + 16), (bx + 7, bar.bottom + 16)])
                self.text("your normal", (bx, bar.bottom + 18), self.F_M, ACCENT, "midtop", s)
            self.text(f"{lm if lm is not None else '-'}", (rc.x + 18, rc.y + 300), self.F_MXL, c, surf=s)
            self.text(f"logMAR  ≈ {core.snellen(lm) or '-'} at 40 cm", (rc.x + 130, rc.y + 314), self.F_B, TEXT, surf=s)
            if base and base.get("na_logmar_" + e) is not None and lm is not None:
                diff = round((lm - base["na_logmar_" + e]) * 10)
                self.text(f"{abs(diff)} line{'s' if abs(diff) != 1 else ''} {'worse' if diff > 0 else 'better'} than your normal" if diff else "same as your normal",
                          (rc.x + 18, rc.y + 372), self.F_S, RED if diff >= 2 else MUTED, surf=s)
            if r.get("na_floor"):
                self.text("hit this screen's smallest letter (may be even sharper)", (rc.x + 18, rc.y + 400), self.F_M, ACCENT, surf=s)
            stroke = self.e_pixels(lm)[0] if (lm is not None and self.store.get("calib")) else 0
            if stroke:
                box = pygame.Rect(rc.right - 18 - 90, rc.y + 290, 90, 90)
                pygame.draw.rect(s, (245, 245, 245), box, border_radius=10)
                self.draw_e(box.center, stroke, "right", surf=s)
        y += 458
        # gap + trend
        gr = pygame.Rect(x0, y, cw, 300)
        self.panel(gr, s)
        self.text("LEFT VS RIGHT EYE", (gr.x + 18, gr.y + 16), self.F_M, MUTED, surf=s)
        for j, (lab, val) in enumerate((("Faint-vision gap (left vs right)", f"{row.get('eye_gap_cs', '-')} log"),
                                        ("Near-vision gap (left vs right)", f"{row.get('eye_gap_na', '-')} logMAR"))):
            yy = gr.y + 50 + j * 44
            self.text(lab, (gr.x + 18, yy), self.F_B, MUTED, surf=s)
            self.text(val, (gr.right - 18, yy), self.F_ML, TEXT, "topright", s)
            pygame.draw.line(s, LINE, (gr.x + 18, yy + 36), (gr.right - 18, yy + 36))
        self.para("Why it matters: lighting, screen and tiredness affect both eyes. If only one eye changes, it's probably the eye itself. "
                  "Near vision getting blurrier in both eyes is the classic SANS 'hyperopic shift': try space anticipation glasses.",
                  (gr.x + 18, gr.y + 150), cw - 36, self.F_S, MUTED, 2, s)
        self.para(f"Saved to {os.path.basename(CSV_FILE)} (same columns as the web version; vision_score = mean faint-vision score of both eyes)."
                  if row["status"] != "PRACTICE" else "Practice run: nothing saved.", (gr.x + 18, gr.y + 220), cw - 36, self.F_S, ACCENT, 2, s)
        tr = pygame.Rect(x0 + cw + 18, y, cw, 300)
        self.panel(tr, s)
        self.text("TREND", (tr.x + 18, tr.y + 16), self.F_M, MUTED, surf=s)
        self._trend(s, tr, self.hist(row["crew"]) or [row])

    def _trend(self, s, rect, rows):
        rows = rows[-12:]
        if len(rows) < 2:
            self.text("Do at least 2 scans to see your trend.", rect.center, self.F_B, DIM, "center", s)
            return
        for k, (key, title, fmt) in enumerate((("cs_mean", "FAINT VISION (logCS) · higher = better", "{:.2f}"),
                                               ("na_logmar", "NEAR VISION (logMAR) · lower = sharper", "{:.2f}"))):
            box = pygame.Rect(rect.x + 60, rect.y + 66 + k * 112, rect.w - 80, 70)
            self.text(title, (box.x, box.y - 18), self.F_M, MUTED, surf=s)
            vals = [v for r in rows for v in (core._num(r.get(key + "_R")), core._num(r.get(key + "_L"))) if v is not None]
            if not vals:
                continue
            lo, hi = min(vals) - .05, max(vals) + .05
            X = lambda i: box.x + i * box.w / (len(rows) - 1)
            Y = lambda v: box.bottom - (v - lo) / ((hi - lo) or 1) * box.h
            for g in (lo, (lo + hi) / 2, hi):
                pygame.draw.line(s, (27, 40, 70), (box.x, Y(g)), (box.right, Y(g)))
                self.text(fmt.format(g), (box.x - 6, Y(g)), self.F_M, DIM, "midright", s)
            for e, col in (("R", ORANGE), ("L", ACCENT)):
                pts = [(X(i), Y(core._num(r.get(key + "_" + e)))) for i, r in enumerate(rows) if core._num(r.get(key + "_" + e)) is not None]
                if len(pts) > 1:
                    pygame.draw.lines(s, col, False, pts, 3)
                for (px, py), r in zip(pts, rows):
                    pygame.draw.circle(s, col, (int(px), int(py)), 5, 2 if r.get("data_source") == "simulated" else 0)
        self.text("right eye", (rect.x + 60, rect.bottom - 24), self.F_M, ORANGE, surf=s)
        self.text("left eye", (rect.x + 170, rect.bottom - 24), self.F_M, ACCENT, surf=s)
        self.text("hollow = simulated", (rect.x + 270, rect.bottom - 24), self.F_M, MUTED, surf=s)

    # ============================================================ MAIN
    def run(self):
        msg = ("", TEXT)
        while True:
            action = self.home(msg)
            msg = ("", TEXT)
            try:
                if action == "start":
                    self.run_scan()
                else:
                    self.run_demo()
                self.ci = {"queasy": None, "glasses": None, "practice": self.ci["practice"]}
            except Abort:
                self.progress = None
                msg = ("Scan aborted. Nothing saved.", AMBER)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--windowed", action="store_true", help="1280x800 window instead of full screen")
    App(ap.parse_args().windowed).run()
