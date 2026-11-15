"""
COMMS CHECK - hearing-in-noise game (pygame). Part of Mission Pulse.

Install once:   pip install pygame numpy
Run:            python comms_app.py               (full screen)
                python comms_app.py --windowed    (1280x800 window)
Needs comms_core.py in the same folder, and HEADPHONES (each ear is tested on its own).

The voice: the folder  comms_voice/  (0.wav ... 9.wav) ships with the game: the CMU Flite "kal" voice (built from real recorded speech), the same one as
the web prototype. Keep that folder next to this file. To use a teammate's real voice instead, record 0.wav ... 9.wav
(16-bit PCM WAV, one digit per file) and replace the files. Use the same voice files on every computer.
If the folder is missing, the game tries your computer's own speech engine (Windows / Mac / Linux) to make one.
  python comms_app.py --rebuild-voice   replaces comms_voice/ with your computer's speech engine voice.

Files it creates next to this script:
  commscheck_history.json   saved scans per crew ID
  commscheck_scans.csv      every saved scan (columns: see comms_core.COLS)
Keys: number keys = type digits  ·  BACKSPACE = delete  ·  ESC = abort / quit  ·  M = mute effects
"""

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime

import numpy as np
import pygame

import comms_core as core
from comms_core import CFG as C

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(HERE, "commscheck_history.json")
CSV_FILE = os.path.join(HERE, "commscheck_scans.csv")
VOICE_DIR = os.path.join(HERE, "comms_voice")
HEADER_H = 64
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]

BG = (5, 7, 15); PANEL = (13, 20, 38); PANEL2 = (19, 29, 53); LINE = (36, 49, 90)
TEXT = (232, 237, 251); MUTED = (138, 150, 182); DIM = (86, 97, 127)
ACCENT = (79, 209, 255); GOLD = (255, 209, 102); GREEN = (61, 220, 132); AMBER = (255, 181, 71); RED = (255, 93, 108)
PHOS = (80, 255, 160); PHOS_DIM = (20, 70, 45); SCOPE_BG = (4, 18, 12); ORANGE = (255, 123, 84); BLUE = (79, 170, 255)
STATUS_COL = {"GO": GREEN, "CHECK": AMBER, "HEARING CHECK": RED, "RETEST": MUTED, "PRACTICE": ACCENT}


class Abort(Exception):
    pass


# ============================================================ voice files
def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif sw == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        x = ((b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)) << 8 >> 8).astype(np.float32) / 8388608
    elif sw == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError("unsupported WAV")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def resample(x, sr_in, sr_out):
    if sr_in == sr_out:
        return x
    n = int(len(x) * sr_out / sr_in)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def voice_ok(folder):
    for d in range(10):
        p = os.path.join(folder, f"{d}.wav")
        try:
            x, sr = read_wav(p)
            if not (0.12 < len(x) / sr < 3.0) or np.abs(x).max() < 0.01:
                return False
        except Exception:
            return False
    return True


def make_computer_voice(folder):
    """Ask the operating system's own speech engine to say 0-9. Returns the engine name, or None."""
    os.makedirs(folder, exist_ok=True)
    paths = [os.path.join(folder, f"{d}.wav") for d in range(10)]
    tries = []
    if sys.platform.startswith("win"):
        def win():
            lines = ["Add-Type -AssemblyName System.Speech", "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer", "$s.Rate = -1"]
            for p, wd in zip(paths, WORDS):
                lines += [f"$s.SetOutputToWaveFile('{p.replace(chr(39), chr(39) * 2)}')", f"$s.Speak('{wd}')"]
            lines += ["$s.SetOutputToNull()", "$s.Dispose()"]
            fd, ps1 = tempfile.mkstemp(suffix=".ps1")
            with os.fdopen(fd, "w") as fh:
                fh.write("\n".join(lines))
            try:
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1], check=True, timeout=90,
                               capture_output=True)
            finally:
                os.remove(ps1)
        tries.append(("Windows speech", win))
    if shutil.which("say"):
        tries.append(("macOS say", lambda: [subprocess.run(["say", "-r", "160", "-o", p, "--data-format=LEI16@22050", wd], check=True, timeout=30)
                                           for p, wd in zip(paths, WORDS)]))
    for exe in ("espeak-ng", "espeak"):
        if shutil.which(exe):
            tries.append((exe, lambda exe=exe: [subprocess.run([exe, "-s", "140", "-w", p, wd], check=True, timeout=30) for p, wd in zip(paths, WORDS)]))
    if shutil.which("pico2wave"):
        tries.append(("pico2wave", lambda: [subprocess.run(["pico2wave", "-w", p, wd], check=True, timeout=30) for p, wd in zip(paths, WORDS)]))

    def ttsx():
        import pyttsx3
        eng = pyttsx3.init()
        eng.setProperty("rate", 150)
        for p, wd in zip(paths, WORDS):
            eng.save_to_file(wd, p)
        eng.runAndWait()
    tries.append(("pyttsx3", ttsx))
    for name, fn in tries:
        try:
            fn()
            if voice_ok(folder):
                return name
        except Exception:
            pass
    return None


# ============================================================ audio
class Audio:
    def __init__(self):
        self.ok, self.sr, self.channels = False, 44100, 2
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            sr, _, ch = pygame.mixer.get_init()
            self.ok, self.sr, self.channels = True, sr, ch
        except Exception:
            pass
        self.chan, self.snd, self.t0, self.dur, self.mono = None, None, None, 0.0, None

    def _sound(self, stereo):
        if self.channels == 1:
            stereo = stereo.max(axis=1, keepdims=True) + stereo.min(axis=1, keepdims=True)
        elif self.channels > 2:
            stereo = np.concatenate([stereo, np.zeros((len(stereo), self.channels - 2), np.int16)], axis=1)
        return pygame.mixer.Sound(buffer=np.ascontiguousarray(stereo, dtype=np.int16).tobytes())

    def play(self, stereo, mono):
        self.stop()
        self.mono, self.dur, self.t0 = mono, len(mono) / self.sr, pygame.time.get_ticks() / 1000
        if self.ok:
            try:
                self.snd = self._sound(stereo)
                self.chan = self.snd.play()
            except Exception:
                pass

    def pos(self):
        return None if self.t0 is None else pygame.time.get_ticks() / 1000 - self.t0

    def playing(self):
        p = self.pos()
        return p is not None and p < self.dur

    def stop(self):
        if self.chan is not None:
            try:
                self.chan.stop()
            except Exception:
                pass
        self.chan, self.t0 = None, None

    def window(self, n=1400):
        """Samples around the current playback point (for the oscilloscope)."""
        p = self.pos()
        if p is None or self.mono is None or p >= self.dur:
            return None
        i = int(p * self.sr)
        seg = self.mono[max(0, i - n): i]
        return seg if len(seg) > 10 else None


# ============================================================ app
class App:
    def __init__(self, windowed=False, rebuild_voice=False):
        pygame.init()
        self.audio = Audio()
        self.screen = pygame.display.set_mode((1280, 800)) if windowed else pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("COMMS CHECK - Hearing in Noise")
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
        self.F_MXL = pygame.font.SysFont(m, 44, bold=True)
        self.F_CODE = pygame.font.SysFont(m, 64, bold=True)
        rnd = random.Random(7)
        self.stars = [(rnd.randrange(self.w), rnd.randrange(self.h), rnd.choice([1, 1, 2])) for _ in range(90)]
        self.rng = random.Random()
        self.store = self._load()
        self.muted = False
        self.crew = "AST-01"
        self.ci = {"room": None, "phones": None, "practice": False}
        self.progress = None
        self.title, self.sub = "COMMS CHECK", "daily hearing check"
        self.mute_rect = pygame.Rect(0, 0, 0, 0)
        self._init_sfx()
        self.voice, self.voice_src = None, ""
        self._prepare_voice(rebuild_voice)

    # ------------------------------------------------ storage
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
                t = core.to_csv([row])
                fh.write(t if new else t.split("\n", 1)[1])
        except OSError:
            pass

    # ------------------------------------------------ sound effects (both ears, only between codes)
    def _init_sfx(self):
        self.sounds = {}
        if not self.audio.ok:
            return
        sr = self.audio.sr

        def tone(f0, f1, dur, vol=0.18, kind="sin"):
            n = int(sr * dur)
            t = np.arange(n) / sr
            ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, n)) / sr
            wv = np.sin(ph) if kind == "sin" else np.sign(np.sin(ph)) * 0.5
            return wv * np.exp(-4 * t / dur) * vol

        def snd(*parts):
            x = (np.concatenate(parts) * 32767).astype(np.int16)
            return self.audio._sound(np.stack([x, x], axis=1))
        try:
            crackle = np.random.default_rng(3).standard_normal(int(sr * .12)) * np.exp(-np.arange(int(sr * .12)) / (sr * .03)) * .08
            self.sounds = {"lock": snd(tone(880, 880, .07), tone(1320, 1320, .1)), "miss": snd(tone(240, 150, .22, .14, "sq")),
                           "chime": snd(tone(660, 660, .12), tone(990, 990, .22)), "crackle": snd(crackle),
                           "scan": snd(tone(200, 900, .5, .1))}
        except Exception:
            self.sounds = {}

    def sfx(self, name):
        if not self.muted and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass

    # ------------------------------------------------ voice
    def _prepare_voice(self, rebuild):
        if rebuild or not voice_ok(VOICE_DIR):
            self.background()
            self.text("Setting up the Mission Control voice...", (self.w // 2, self.h // 2 - 20), self.F_H2, TEXT, "center")
            self.text("(first run only: using your computer's built-in speech engine)", (self.w // 2, self.h // 2 + 24), self.F_S, MUTED, "center")
            pygame.display.flip()
            eng = make_computer_voice(VOICE_DIR)
            self.voice_src = f"computer voice ({eng})" if eng else ""
        else:
            self.voice_src = "voice files in comms_voice/"
        if voice_ok(VOICE_DIR):
            waves = {}
            for d in range(10):
                x, sr = read_wav(os.path.join(VOICE_DIR, f"{d}.wav"))
                waves[str(d)] = resample(x, sr, self.audio.sr)
            self.voice = core.Voice(waves, self.audio.sr)

    # ------------------------------------------------ drawing helpers
    def text(self, msg, pos, font=None, color=TEXT, anchor="topleft", surf=None):
        s = (font or self.F_B).render(str(msg), True, color)
        r = s.get_rect(**{anchor: pos})
        (surf or self.screen).blit(s, r)
        return r

    def wrap(self, msg, font, width):
        words, lines, cur = str(msg).split(" "), [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if font.size(t)[0] > width and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines

    def para(self, msg, pos, width, font=None, color=TEXT, gap=6, surf=None, center=False):
        font = font or self.F_B
        x, y = pos
        for line in self.wrap(msg, font, width):
            self.text(line, (x, y), font, color, "midtop" if center else "topleft", surf)
            y += font.get_linesize() + gap
        return y

    def panel(self, rect, surf=None, border=LINE, fill=PANEL, width=1, radius=16):
        surf = surf or self.screen
        pygame.draw.rect(surf, fill, rect, border_radius=radius)
        pygame.draw.rect(surf, border, rect, width, border_radius=radius)

    def button(self, label, center, color=ACCENT, fg=(3, 16, 28), enabled=True, w=None, font=None, surf=None):
        font = font or self.F_BB
        r = pygame.Rect(0, 0, w or font.size(label)[0] + 44, 52)
        r.center = center
        pygame.draw.rect(surf or self.screen, color if enabled else (60, 70, 95), r, border_radius=12)
        self.text(label, r.center, font, fg if enabled else MUTED, "center", surf)
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

    def logo(self, x, y, surf=None):
        surf = surf or self.screen
        for i, r in enumerate((6, 11, 16)):
            pygame.draw.arc(surf, ACCENT if i < 2 else GOLD, (x - r, y - r, 2 * r, 2 * r), -0.8, 0.8, 3)
        pygame.draw.circle(surf, GOLD, (x - 2, y), 4)

    def header(self):
        pygame.draw.rect(self.screen, (7, 11, 24), (0, 0, self.w, HEADER_H))
        pygame.draw.line(self.screen, LINE, (0, HEADER_H - 1), (self.w, HEADER_H - 1))
        self.logo(30, 32)
        self.text("COMMS CHECK", (58, 20), self.F_BB)
        self.text(self.title, (232, 12), self.F_BB)
        self.text(self.sub, (232, 38), self.F_M, MUTED)
        self.mute_rect = pygame.Rect(0, 0, 110, 28)
        self.mute_rect.midright = (self.w - 20, 32)
        pygame.draw.rect(self.screen, LINE, self.mute_rect, 1, border_radius=6)
        self.text("SFX OFF" if self.muted else "SFX ON", self.mute_rect.center, self.F_M, MUTED, "center")
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
                self.audio.stop()
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
            elif e.type == pygame.MOUSEWHEEL:
                out.append(("wheel", e.y, None))
        return out

    def flip(self):
        pygame.display.flip()
        self.clock.tick(60)

    def now(self):
        return pygame.time.get_ticks() / 1000

    def headphones(self, center, ear, scale=1.0, surf=None):
        """Headphone icon; the tested side glows. ear: 'left', 'right' or None. Drawn as worn (your left = screen left)."""
        surf = surf or self.screen
        cx, cy = center
        R = int(70 * scale)
        pygame.draw.arc(surf, MUTED, (cx - R, cy - R, 2 * R, 2 * R), 0.15, math.pi - 0.15, max(3, int(8 * scale)))
        for side, sx in (("left", -1), ("right", 1)):
            on = ear == side
            cup = pygame.Rect(0, 0, int(36 * scale), int(62 * scale))
            cup.center = (cx + sx * (R - int(6 * scale)), cy + int(16 * scale))
            if on:
                for k in range(3, 0, -1):
                    pygame.draw.rect(surf, (20 + 15 * k, 60 + 30 * k, 50 + 20 * k), cup.inflate(10 * k, 10 * k), border_radius=int(16 * scale) + 4 * k)
            pygame.draw.rect(surf, GREEN if on else PANEL2, cup, border_radius=int(14 * scale))
            pygame.draw.rect(surf, GREEN if on else LINE, cup, 2, border_radius=int(14 * scale))
            self.text("L" if side == "left" else "R", cup.center, self.F_BB if scale >= 1 else self.F_M, (4, 30, 18) if on else MUTED, "center", surf)

    # ================================================================ HOME
    def home(self, message=("", TEXT)):
        typing, clear_armed = False, False
        while True:
            self.typing = typing
            self.background()
            self.title, self.sub, self.progress = "COMMS CHECK", "daily hearing check", None
            self.header()
            x0 = max(40, (self.w - 1150) // 2)
            self.text("Mission Control is calling.", (x0, 90), self.F_H1)
            self.para("One quick game (~2.5 min) checks how well each ear picks speech out of noise, the hearing skill "
                      "astronauts rely on all day. Each ear is compared with its own normal and with the other ear.",
                      (x0, 148), 1000, self.F_B, MUTED)
            left = pygame.Rect(x0, 228, 600, 410)
            right = pygame.Rect(x0 + 620, 228, 530, 410)
            self.panel(left, fill=PANEL2)
            self.text("CREW ID", (left.x + 20, left.y + 18), self.F_M, MUTED)
            field = pygame.Rect(left.x + 20, left.y + 42, 200, 40)
            pygame.draw.rect(self.screen, (10, 17, 32), field, border_radius=8)
            pygame.draw.rect(self.screen, ACCENT if typing else LINE, field, 2 if typing else 1, border_radius=8)
            self.text(self.crew + ("|" if typing and (pygame.time.get_ticks() // 500) % 2 else ""), (field.x + 10, field.centery), self.F_ML, TEXT, "midleft")
            self.text("HOW NOISY IS IT AROUND YOU RIGHT NOW?", (left.x + 20, left.y + 104), self.F_M, MUTED)
            rc, cx = [], left.x + 20
            for v, lab in (("quiet", "Quiet"), ("normal", "Normal hum (fans)"), ("loud", "Loud (exercise, machines)")):
                r = self.chip(lab, (cx, left.y + 128), self.ci["room"] == v)
                rc.append((r, v))
                cx = r.right + 8
            if self.ci["room"] == "loud":
                self.text("Too loud: results will be greyed out. Move somewhere quieter if you can.", (left.x + 20, left.y + 170), self.F_S, AMBER)
            self.text("SAME HEADPHONES AS USUAL?", (left.x + 20, left.y + 204), self.F_M, MUTED)
            pc, cx = [], left.x + 20
            for v, lab in (("yes", "Yes"), ("first", "First scan"), ("no", "No, different ones")):
                r = self.chip(lab, (cx, left.y + 228), self.ci["phones"] == v)
                pc.append((r, v))
                cx = r.right + 8
            self.text("Same headphones + same volume every day = comparable scans.", (left.x + 20, left.y + 272), self.F_S, MUTED)
            self.text("MODE", (left.x + 20, left.y + 306), self.F_M, MUTED)
            m1 = self.chip("MISSION (saved)", (left.x + 20, left.y + 330), not self.ci["practice"])
            m2 = self.chip("PRACTICE (not saved)", (m1.right + 8, left.y + 330), self.ci["practice"])
            self.text(f"Voice: {self.voice_src}" if self.voice else "Voice: NOT FOUND (see the message on Start)", (left.x + 20, left.y + 376),
                      self.F_S, MUTED if self.voice else RED)
            top = pygame.Rect(right.x, right.y, right.w, 170)
            self.panel(top, fill=PANEL2)
            self.text("TODAY'S TRANSMISSION", (top.x + 20, top.y + 16), self.F_M, MUTED)
            self.text("COMMS CHECK", (top.x + 20, top.y + 44), self.F_BB)
            self.text("decode codes through static", (top.right - 20, top.y + 46), self.F_S, MUTED, "topright")
            self.text("Channel check -> right ear -> left ear", (top.x + 20, top.y + 84), self.F_B)
            self.text("Put your HEADPHONES on. About 2.5 minutes.", (top.x + 20, top.y + 124), self.F_S, MUTED)
            rec = pygame.Rect(right.x, right.y + 186, right.w, 224)
            self.panel(rec, fill=PANEL2)
            h = self.hist()
            valid = sum(1 for r in h if int(r.get("valid", 0) or 0) == 1)
            base = core.baseline(h)
            nsim = sum(1 for r in h if r.get("data_source") == "simulated")
            self.text("CREW RECORD", (rec.x + 20, rec.y + 16), self.F_M, MUTED)
            lines = [f"{len(h)} saved scans" + (f" ({nsim} simulated)" if nsim else ""),
                     f"Personal baseline: ACTIVE ({base['n']} valid scans)" if base else f"Personal baseline: forming ({valid}/{C['BASELINE_MIN']})",
                     f"Last result: {h[-1].get('status')} ({str(h[-1].get('timestamp'))[:10]})" if h else "No scans yet"]
            for i, l in enumerate(lines):
                self.text(l, (rec.x + 20, rec.y + 44 + i * 30), self.F_B, GREEN if (i == 1 and base) else TEXT)
            b_hist = self.chip("Load demo history (simulated)", (rec.x + 20, rec.y + 150))
            b_clear = self.chip("Click again to delete" if clear_armed else "Clear history", (b_hist.right + 10, rec.y + 150))
            by = left.bottom + 50
            b_start = self.button("Start hearing scan  >", (x0 + 140, by))
            b_demo = self.button("Demo: simulated day-140 astronaut", (b_start.right + 210, by), GOLD, (40, 28, 0), font=self.F_S)
            self.text(message[0], (x0, by + 38), self.F_S, message[1])
            self.para("Screening and education demo, not a medical device and not validated. It can't diagnose hearing loss: "
                      "it flags when to get a proper hearing test. Keys: number keys, BACKSPACE, ESC, M = mute effects.",
                      (x0, self.h - 56), 1100, self.F_S, DIM, 2)
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
                        self.audio.stop()
                        pygame.quit()
                        sys.exit()
                    if a == pygame.K_RETURN:
                        kind, a = "click", b_start.center
                if kind != "click":
                    continue
                if not self.crew:
                    self.crew = "AST-01"
                typing = field.collidepoint(a)
                for r, v in rc:
                    if r.collidepoint(a):
                        self.ci["room"] = v
                for r, v in pc:
                    if r.collidepoint(a):
                        self.ci["phones"] = v
                if m1.collidepoint(a):
                    self.ci["practice"] = False
                if m2.collidepoint(a):
                    self.ci["practice"] = True
                if b_hist.collidepoint(a):
                    self.set_hist(core.make_demo_history(self.crew, rng=random.Random(1)))
                    message = (f"Loaded 6 SIMULATED healthy scans for {self.crew}. Personal baseline is now active.", ACCENT)
                if b_clear.collidepoint(a):
                    if clear_armed:
                        self.set_hist([])
                        message = (f"History cleared for {self.crew}.", ACCENT)
                    clear_armed = not clear_armed
                    continue
                clear_armed = False
                if b_demo.collidepoint(a):
                    return "demo"
                if b_start.collidepoint(a):
                    if self.voice is None:
                        message = ("No voice found. Put 0.wav ... 9.wav (one spoken digit each) in the comms_voice folder, then restart.", RED)
                    elif self.ci["room"] is None or self.ci["phones"] is None:
                        message = ("Please answer both questions first.", AMBER)
                    else:
                        return "start"

    # ================================================================ generic "press to continue" screen
    def wait_continue(self, draw, label="Continue  (SPACE)", extra=None):
        while True:
            self.background()
            self.header()
            bottom = draw()
            b = self.button(label, (self.w // 2, min(self.h - 50, bottom + 46)))
            self.flip()
            for kind, a, _ in self.events():
                if kind == "key" and a == pygame.K_ESCAPE:
                    raise Abort()
                if (kind == "key" and a in (pygame.K_SPACE, pygame.K_RETURN)) or (kind == "click" and b.collidepoint(a)):
                    return
                if extra:
                    extra(kind, a)

    # ================================================================ CHANNEL CHECK + VOLUME
    def channel_check(self):
        self.title, self.sub = "CHANNEL CHECK", "headphones + volume"
        fails, msg = 0, None
        while True:
            ear = self.rng.choice(["left", "right"])
            st, mono, _ = core.build_trial_audio(self.voice, "", 0, ear, self.rng, static_only_s=2.2)
            next_play, answered = 0.0, None
            while answered is None:
                t = self.now()
                if t >= next_play:
                    self.audio.play(st, mono)
                    next_play = t + 2.6
                self.background()
                self.header()
                cx = self.w // 2
                self.text("CHANNEL CHECK", (cx, 104), self.F_M, GOLD, "midtop")
                self.text("Where is the static coming from?", (cx, 130), self.F_H1, TEXT, "midtop")
                self.para("Static is playing in ONE earphone. Tap the side you hear it in. This makes sure your headphones aren't "
                          "on backwards. Can't hear anything? Turn your computer volume up.", (cx, 196), 820, self.F_B, MUTED, center=True)
                self.headphones((cx, 380), None, 1.4)
                self.scope(pygame.Rect(cx - 160, 470, 320, 70), self.audio.window(), small=True)
                bl = self.button("<  LEFT ear", (cx - 170, 600), w=240)
                br = self.button("RIGHT ear  >", (cx + 170, 600), w=240)
                if msg:
                    self.para(msg[0], (cx, 650), 900, self.F_B, msg[1], center=True)
                self.flip()
                for kind, a, _ in self.events():
                    if kind == "key" and a == pygame.K_ESCAPE:
                        self.audio.stop()
                        raise Abort()
                    if (kind == "key" and a in (pygame.K_LEFT, pygame.K_a)) or (kind == "click" and bl.collidepoint(a)):
                        answered = "left"
                    if (kind == "key" and a in (pygame.K_RIGHT, pygame.K_d)) or (kind == "click" and br.collidepoint(a)):
                        answered = "right"
            self.audio.stop()
            if answered == ear:
                self.sfx("lock")
                break
            fails += 1
            self.sfx("miss")
            if fails >= 2:
                result = "fail"
                self.wait_continue(lambda: self.para("Still the wrong side. Your headphones may be swapped, or one earphone isn't working. "
                                                     "You can continue, but this scan will be greyed out.", (self.w // 2, 300), 800,
                                                     self.F_H2, AMBER, center=True), "Continue anyway  (SPACE)")
                return result
            msg = (f"Hmm, it was in your {ear.upper()} ear. Are your headphones on backwards? Check the L and R marks and try again.", AMBER)
        # meet the voice + set the volume: a sample code, first with NO static, then with light static, digits shown as spoken
        sample = {}

        def make_sample():
            code = "".join(self.rng.sample(C["DIGITS"], 3))
            a, m1, on1 = core.build_trial_audio(self.voice, code, None, "both", self.rng)
            gap = np.zeros((int(self.audio.sr * 0.6), 2), np.int16)
            b, m2, on2 = core.build_trial_audio(self.voice, code, C["WARMUP_SNR"], "both", self.rng)
            off = (len(a) + len(gap)) / self.audio.sr
            sample.update(code=code, st=np.concatenate([a, gap, b]), mono=np.concatenate([m1, np.zeros(len(gap), np.float32), m2]),
                          on=on1 + [o + off for o in on2], split=off)
            self.audio.play(sample["st"], sample["mono"])

        def draw():
            cx = self.w // 2
            self.text("CHANNEL CHECK PASSED", (cx, 92), self.F_M, GREEN, "midtop")
            self.text("Meet Mission Control + set the volume", (cx, 116), self.F_H1, TEXT, "midtop")
            self.para("Listen to the sample: the code is read once with NO static, then once WITH light static. Turn your volume "
                      "until the voice is easy to hear. Then DON'T touch the volume during the scan (use the same level every day).",
                      (cx, 180), 900, self.F_B, MUTED, center=True)
            p = self.audio.pos()
            k = 0 if p is None else sum(1 for o in sample["on"] if p >= o)
            phase = "" if p is None or p > self.audio.dur else ("VOICE ONLY" if p < sample["split"] else "WITH STATIC")
            self.text(phase or "press P to hear it again", (cx, 292), self.F_M, GOLD if phase else DIM, "midtop")
            for n in range(3):
                r = pygame.Rect(cx - 190 + n * 132, 318, 112, 120)
                lit = (k > n and k <= 3) or (k > 3 + n)
                pygame.draw.rect(self.screen, PANEL2, r, border_radius=14)
                pygame.draw.rect(self.screen, GREEN if lit else LINE, r, 3 if lit else 2, border_radius=14)
                self.text(sample["code"][n], r.center, self.F_CODE, TEXT if lit else DIM, "center")
            self.scope(pygame.Rect(cx - 220, 466, 440, 90), self.audio.window(), small=True)
            self.sample_btn = self.button("Play sample  (P)", (cx, 600), PANEL2, TEXT, w=260)
            return 640

        def extra(kind, a):
            if (kind == "click" and self.sample_btn.collidepoint(a)) or (kind == "key" and a == pygame.K_p):
                make_sample()
        make_sample()
        self.wait_continue(draw, "Volume is set  (SPACE)", extra)
        self.audio.stop()
        return "pass"

    # ================================================================ BRIEFING + EAR PROMPT
    def briefing(self):
        self.title, self.sub = "MISSION BRIEFING", "COMMS CHECK"
        lines = ["Mission Control sends a 3-digit code through radio static, into ONE earphone.",
                 "Type the 3 digits you heard: number keys or the keypad on screen.",
                 "Decode it and the next code has MORE static. Miss, and the static drops.",
                 "It's MEANT to get hard: the static rises until you miss about half. Can't make it out? GUESS.",
                 "One ear at a time, about a minute each. Don't touch the volume."]

        def draw():
            cx = self.w // 2
            self.text("HEARING · SPEECH IN NOISE", (cx, 92), self.F_M, GOLD, "midtop")
            self.text("COMMS CHECK", (cx, 112), self.F_H1, ACCENT, "midtop")
            art = pygame.Rect(cx - 260, 172, 520, 150)
            self.panel(art, fill=PANEL)
            self.scope(pygame.Rect(art.x + 20, art.y + 20, 250, 110), self.demo_wave(), small=True)
            for i, ch in enumerate("4 9 2".split()):
                r = pygame.Rect(art.x + 300 + i * 70, art.y + 30, 58, 70)
                pygame.draw.rect(self.screen, PANEL2, r, border_radius=10)
                pygame.draw.rect(self.screen, GREEN, r, 2, border_radius=10)
                self.text(ch, r.center, self.F_MXL, TEXT, "center")
            self.text("DECODED", (art.x + 405, art.y + 112), self.F_M, GREEN, "midtop")
            box = pygame.Rect(cx - 470, 340, 940, 26 + len(lines) * 40)
            self.panel(box, fill=PANEL2)
            for i, l in enumerate(lines):
                pygame.draw.circle(self.screen, GOLD, (box.x + 30, box.y + 28 + i * 40), 5)
                self.text(l, (box.x + 50, box.y + 16 + i * 40), self.F_B)
            return self.para("Why: constant fan noise on the station can slowly damage hearing, and normal beep tests need a quiet "
                             "room. This checks the skill astronauts rely on most: understanding speech through noise.",
                             (cx, box.bottom + 16), 900, self.F_S, MUTED, center=True)
        self.wait_continue(draw, "Got it  (SPACE)")

    def demo_wave(self):
        t = self.now()
        x = np.arange(700)
        return (np.sin(x / 7 + t * 9) * np.sin(x / 90 + t) * .5 + np.sin(x * 1.7 + t * 40) * .15) * .25

    def ear_prompt(self, ear):
        self.title, self.sub = "COMMS CHECK", f"{ear.upper()} EAR"

        def draw():
            cx = self.w // 2
            self.headphones((cx, 250), ear, 1.6)
            self.text(f"Testing your {ear.upper()} ear", (cx, 380), self.F_H1, TEXT, "midtop")
            self.para(f"Codes play ONLY in your {ear} earphone. Keep both earphones on, eyes on the screen, fingers on the "
                      "number keys.", (cx, 444), 760, self.F_B, MUTED, center=True)
            return 530
        self.wait_continue(draw, "Open channel  (SPACE)")

    # ================================================================ PLAY
    def scope(self, rect, seg, small=False, surf=None):
        surf = surf or self.screen
        pygame.draw.rect(surf, SCOPE_BG, rect, border_radius=10)
        for i in range(1, 6):
            x = rect.x + rect.w * i // 6
            pygame.draw.line(surf, PHOS_DIM, (x, rect.y + 4), (x, rect.bottom - 4))
        for i in range(1, 4):
            y = rect.y + rect.h * i // 4
            pygame.draw.line(surf, PHOS_DIM, (rect.x + 4, y), (rect.right - 4, y))
        mid = rect.centery
        if seg is None or len(seg) < 4:
            jitter = [mid + int(math.sin(i * 1.3 + self.now() * 6) * 1.5) for i in range(0, rect.w - 12, 6)]
            pts = [(rect.x + 6 + i * 6, y) for i, y in enumerate(jitter)]
        else:
            n = rect.w - 12
            idx = np.linspace(0, len(seg) - 1, n).astype(int)
            g = 0.45 * rect.h / 0.5
            ys = np.clip(mid - seg[idx] * g, rect.y + 3, rect.bottom - 3)
            pts = [(rect.x + 6 + i, int(y)) for i, y in enumerate(ys)]
        if len(pts) > 1:
            pygame.draw.lines(surf, PHOS, False, pts, 2)
        pygame.draw.rect(surf, (30, 90, 60), rect, 2, border_radius=10)

    def signal_bars(self, x, y, snr):
        lvl = 0 if snr is None else int(round(np.interp(snr, [-14, 8], [1, 5])))
        for i in range(5):
            h = 10 + i * 8
            r = pygame.Rect(x + i * 16, y + 44 - h, 11, h)
            pygame.draw.rect(self.screen, GREEN if i < lvl else LINE, r, border_radius=2)

    def play_ear(self, ear, start_frac):
        test = core.DigitsTest(ear, self.rng)
        self.title, self.sub = "COMMS CHECK", f"{ear.upper()} EAR · decoding"
        W, H = self.w, self.h
        con = pygame.Rect((W - 1180) // 2, HEADER_H + 26, 1180, H - HEADER_H - 60)
        left = pygame.Rect(con.x + 24, con.y + 24, 560, con.h - 48)
        rightx = left.right + 40
        slots = [pygame.Rect(rightx + 40 + i * 132, con.y + 70, 112, 132) for i in range(3)]
        kw, kh, gap = 116, 70, 14
        kx0, ky0 = rightx + 40, con.y + 300
        keys = []
        for i, lab in enumerate(["1", "2", "3", "4", "5", "6", "7", "8", "9", "DEL", "0", "CLR"]):
            keys.append((pygame.Rect(kx0 + (i % 3) * (kw + gap), ky0 + (i // 3) * (kh + gap), kw, kh), lab))
        state, t_state, trial, typed, fb, hits = "gap", self.now(), None, "", None, 0
        log = []
        pressed = None
        dial_phase = self.rng.random() * 10
        while True:
            t = self.now()
            # ---------------- state machine
            if state == "gap" and t - t_state >= C["GAP_S"]:
                trial = test.next_trial()
                if trial is None:
                    break
                st, mono, _ = core.build_trial_audio(self.voice, trial.digits, trial.snr, ear, self.rng)
                self.audio.play(st, mono)
                state, t_state, typed = "play", t, ""
            elif state == "play" and not self.audio.playing():
                state, t_state = "respond", t
            elif state == "respond" and t - t_state >= C["RESP_TIMEOUT_S"]:
                self._submit(test, trial, typed, True)
                fb = self._feedback(trial, t, test)
                log.append(trial)
                state, t_state = "gap", t
            submit = False
            for kind, a, uni in self.events():
                if kind == "key" and a == pygame.K_ESCAPE:
                    self.audio.stop()
                    raise Abort()
                lab = None
                if kind == "key":
                    if uni and uni.isdigit():
                        lab = uni
                    elif a == pygame.K_BACKSPACE:
                        lab = "DEL"
                elif kind == "click":
                    for r, l in keys:
                        if r.collidepoint(a):
                            lab = l
                if lab is None or state not in ("play", "respond"):
                    continue
                pressed = (lab, t)
                if lab == "DEL":
                    typed = typed[:-1]
                elif lab == "CLR":
                    typed = ""
                elif lab.isdigit() and len(typed) < 3:
                    typed += lab
                if len(typed) == 3:
                    submit = True
            if submit:
                self.audio.stop()
                self._submit(test, trial, typed, False)
                hits += trial.correct and not trial.warmup
                fb = self._feedback(trial, t, test)
                log.append(trial)
                state, t_state = "gap", t
            # ---------------- draw
            self.progress = start_frac + 0.5 * test.progress
            self.background()
            self.header()
            self.panel(con, fill=(9, 14, 28), border=LINE, radius=22)
            # left: radio unit
            self.panel(left, fill=PANEL, radius=16)
            live = state == "play"
            self.text("INCOMING TRANSMISSION" if live else "CHANNEL OPEN" if state == "respond" else "STANDBY",
                      (left.x + 20, left.y + 16), self.F_M, GREEN if live else MUTED)
            if live and int(t * 3) % 2:
                pygame.draw.circle(self.screen, RED, (left.right - 26, left.y + 24), 7)
            self.text("REC" if live else "", (left.right - 40, left.y + 24), self.F_M, RED, "midright")
            sc = pygame.Rect(left.x + 20, left.y + 46, left.w - 40, 210)
            self.scope(sc, self.audio.window())
            # tuner
            tune = pygame.Rect(left.x + 20, sc.bottom + 22, left.w - 40, 56)
            pygame.draw.rect(self.screen, (8, 12, 24), tune, border_radius=10)
            for i in range(41):
                x = tune.x + 14 + i * (tune.w - 28) // 40
                pygame.draw.line(self.screen, LINE if i % 5 else MUTED, (x, tune.bottom - 10), (x, tune.bottom - (20 if i % 5 else 30)))
            snr = trial.snr if trial is not None else None
            wob = 0 if snr is None else float(np.interp(snr, [-16, 8], [26, 2]))
            nx = tune.centerx + int(math.sin(t * 7 + dial_phase) * wob + math.sin(t * 19) * wob * .3)
            pygame.draw.line(self.screen, ORANGE, (nx, tune.y + 6), (nx, tune.bottom - 6), 3)
            freq = 121.500 + (nx - tune.centerx) * 0.0004
            self.text(f"{freq:7.3f} MHz", (tune.x + 12, tune.y + 6), self.F_M, GOLD)
            # signal + static + ear
            info_y = tune.bottom + 24
            self.text("SIGNAL", (left.x + 20, info_y), self.F_M, MUTED)
            self.signal_bars(left.x + 20, info_y + 20, snr)
            self.text("STATIC", (left.x + 140, info_y), self.F_M, MUTED)
            lvl = 0 if snr is None else float(np.interp(snr, [-16, 8], [1, 0.08]))
            bar = pygame.Rect(left.x + 140, info_y + 34, 180, 14)
            pygame.draw.rect(self.screen, LINE, bar, border_radius=7)
            pygame.draw.rect(self.screen, AMBER if lvl > .6 else ACCENT, (bar.x, bar.y, int(bar.w * lvl), bar.h), border_radius=7)
            self.headphones((left.right - 90, info_y + 34), ear, 0.62)
            self.text("CODE LOG", (left.x + 20, info_y + 84), self.F_M, MUTED)
            for i, tr_ in enumerate(log[-6:]):
                pr = pygame.Rect(left.x + 20 + (i % 3) * 172, info_y + 108 + (i // 3) * 40, 160, 32)
                c = GREEN if tr_.correct else RED
                pygame.draw.rect(self.screen, (12, 40, 28) if tr_.correct else (48, 16, 22), pr, border_radius=16)
                pygame.draw.rect(self.screen, c, pr, 1, border_radius=16)
                self.text(("HIT  " if tr_.correct else "MISS ") + " ".join(tr_.digits), pr.center, self.F_M, c, "center")
            self.text(f"CODES DECODED  {hits}", (left.x + 20, left.bottom - 40), self.F_ML, GOLD)
            if test.combo >= 2:
                self.text(f"COMBO x{test.combo}", (left.right - 20, left.bottom - 36), self.F_BB, GREEN, "topright")
            # right: code slots + keypad
            msg = ("Listen..." if live else "Type the 3 digits" if state == "respond" else "Next code incoming")
            self.text(msg + (" (warm-up)" if trial is not None and trial.warmup and state in ("play", "respond") else ""),
                      (rightx + 40, con.y + 30), self.F_BB, TEXT if state != "gap" else MUTED)
            for i, r in enumerate(slots):
                filled = i < len(typed)
                cur = i == len(typed) and state in ("play", "respond")
                pygame.draw.rect(self.screen, PANEL2, r, border_radius=14)
                pygame.draw.rect(self.screen, ACCENT if cur else GREEN if filled else LINE, r, 3 if cur else 2, border_radius=14)
                if filled:
                    self.text(typed[i], r.center, self.F_CODE, TEXT, "center")
                elif cur and int(t * 2.5) % 2:
                    pygame.draw.rect(self.screen, ACCENT, (r.centerx - 18, r.bottom - 30, 36, 5))
            if state == "respond":
                left_t = max(0.0, 1 - (t - t_state) / C["RESP_TIMEOUT_S"])
                tb = pygame.Rect(slots[0].x, slots[0].bottom + 16, slots[2].right - slots[0].x, 8)
                pygame.draw.rect(self.screen, LINE, tb, border_radius=4)
                pygame.draw.rect(self.screen, AMBER if left_t < .35 else ACCENT, (tb.x, tb.y, int(tb.w * left_t), tb.h), border_radius=4)
                self.text("comm window", (tb.right, tb.bottom + 4), self.F_M, DIM, "topright")
            for r, lab in keys:
                hot = pressed and pressed[0] == lab and t - pressed[1] < .15
                active = state in ("play", "respond")
                pygame.draw.rect(self.screen, (31, 58, 102) if hot else PANEL2, r, border_radius=12)
                pygame.draw.rect(self.screen, GREEN if hot else (ACCENT if active and lab.isdigit() else LINE), r, 2, border_radius=12)
                self.text(lab, r.center, self.F_ML if lab.isdigit() else self.F_M, TEXT if active else DIM, "center")
            if fb and t - fb["t"] < 1.1:
                k = 1 - (t - fb["t"]) / 1.1
                col = tuple(int(c * (0.35 + 0.65 * k)) for c in fb["col"])
                fx = (slots[0].x + slots[2].right) // 2
                self.text(fb["text"], (fx, slots[0].bottom + 26), self.F_H2, col, "center")
                if fb["sub"]:
                    self.text(fb["sub"], (fx, slots[0].bottom + 62), self.F_S, col, "center")
            if not self.audio.ok:
                self.text("NO AUDIO DEVICE FOUND: plug in headphones and restart", (con.centerx, con.bottom + 8), self.F_M, RED, "midtop")
            self.flip()
        self.audio.stop()
        return test.results()

    def _submit(self, test, trial, typed, timed_out):
        test.answer(trial, typed, timed_out)

    def _feedback(self, trial, t, test):
        if trial.correct:
            self.sfx("lock")
            return {"t": t, "text": "WARM-UP DECODED" if trial.warmup else "TRANSMISSION DECODED",
                    "sub": f"COMBO x{test.combo}  ·  more static next" if test.combo >= 2 else "more static next", "col": GREEN}
        self.sfx("miss")
        return {"t": t, "text": "SIGNAL LOST" if not trial.timed_out else "CHANNEL TIMED OUT",
                "sub": f"code was {' '.join(trial.digits)}  ·  less static next", "col": RED}

    # ================================================================ REVEAL (per ear)
    def meter(self, rect, srt, base=None, color=GREEN, surf=None):
        """Horizontal 'static tolerance' meter: left = weak (+6 dB), right = strong (-16 dB)."""
        surf = surf or self.screen
        lo, hi = 6.0, -16.0
        pos = lambda v: rect.x + int(rect.w * max(0, min(1, (lo - v) / (lo - hi))))
        pygame.draw.rect(surf, LINE, rect, border_radius=rect.h // 2)
        if srt is not None:
            pygame.draw.rect(surf, color, (rect.x, rect.y, max(rect.h, pos(srt) - rect.x), rect.h), border_radius=rect.h // 2)
        x = pos(C["TYPICAL_SRT"])
        pygame.draw.rect(surf, TEXT, (x - 1, rect.y - 5, 3, rect.h + 10))
        if base is not None:
            x = pos(base)
            pygame.draw.rect(surf, GOLD, (x - 2, rect.y - 7, 4, rect.h + 14))
        self.text("weak", (rect.x, rect.bottom + 6), self.F_M, DIM, surf=surf)
        self.text("strong", (rect.right, rect.bottom + 6), self.F_M, DIM, "topright", surf)

    @staticmethod
    def plain(srt):
        if srt is None:
            return "no score"
        if srt < 0:
            return f"You decoded codes even when the static was {abs(srt):.1f} dB LOUDER than the voice."
        return f"You needed the voice {srt:.1f} dB louder than the static to decode codes."

    def reveal(self, ear, r):
        self.sfx("chime")
        self.title, self.sub = "COMMS CHECK", f"{ear.upper()} EAR COMPLETE"

        def draw():
            cx = self.w // 2
            self.text(f"{ear.upper()} EAR: CHANNEL LOCKED", (cx, 100), self.F_H1, GOLD, "midtop")
            cards = [("STATIC TOLERANCE", f"{r['srt']:+.1f} dB" if r["srt"] is not None else "-", "lower = better hearing in noise"),
                     ("CODES DECODED", f"{r['codes_ok']}/{C['TRIALS'] - 1}", "the static kept rising as you hit"),
                     ("DIGITS RIGHT", f"{round((r['digit_acc'] or 0) * 100)}%", "of every digit you typed")]
            for i, (lab, val, sm) in enumerate(cards):
                rc = pygame.Rect(cx - 465 + i * 315, 180, 300, 170)
                self.panel(rc, fill=PANEL)
                self.text(lab, (rc.centerx, rc.y + 20), self.F_M, MUTED, "midtop")
                self.text(val, (rc.centerx, rc.y + 52), self.F_MXL, ACCENT if i == 0 else TEXT, "midtop")
                self.text(sm, (rc.centerx, rc.y + 122), self.F_S, MUTED, "midtop")
            self.meter(pygame.Rect(cx - 360, 400, 720, 18), r["srt"])
            self.text("white tick = rough typical", (cx, 448), self.F_M, DIM, "midtop")
            y = self.para(self.plain(r["srt"]), (cx, 486), 900, self.F_B, TEXT, center=True)
            if r["quality"] != "ok":
                y = self.para("! " + r["reason"], (cx, y + 8), 900, self.F_B, AMBER, center=True)
            elif r.get("floor"):
                y = self.para("You decoded even the noisiest codes. Your hearing may be even better than this shows.", (cx, y + 8), 900, self.F_S, AMBER, center=True)
            return y + 20
        self.wait_continue(draw)

    # ================================================================ SCAN FLOW
    def run_scan(self):
        started = datetime.now()
        self.progress = 0.0
        check = self.channel_check()
        self.briefing()
        res = {}
        for i, ear in enumerate(("right", "left")):
            self.ear_prompt(ear)
            res[ear] = self.play_ear(ear, i * 0.5)
            self.progress = (i + 1) * 0.5
            self.reveal(ear, res[ear])
        src = "practice" if self.ci["practice"] else "prototype_gameplay"
        self.finish(res["right"], res["left"], src, started, check)

    def run_demo(self):
        h = self.hist()
        if core.baseline(h) is None:
            self.set_hist(h + core.make_demo_history(self.crew, rng=random.Random(1)))
        drng = random.Random(140)                                  # fixed seed: the demo tells the same story every time
        R = core.simulate_ear("right", core.SimListener(-11.0, rng=drng))
        L = core.simulate_ear("left", core.SimListener(core.DEMO_LEFT_DIGIT_SRT, rng=drng))
        self.ci.update(room="normal", phones="yes")
        self.finish(R, L, "simulated", datetime.now(), "pass",
                    note="SIMULATED day-140 astronaut: noise damage in the LEFT ear. Nobody played this session.")

    def finish(self, R, L, source, started, check, note=None):
        self.progress = None
        h = self.hist()
        row = core.build_row(R, L, {"crew": self.crew, "session": len(h) + 1, "timestamp": started.isoformat(timespec="seconds"),
                                    "data_source": source, "version": C["VERSION"], "room_noise": self.ci["room"],
                                    "same_headphones": "yes" if self.ci["phones"] == "first" else self.ci["phones"], "channel_check": check})
        ev = core.evaluate(row, h)
        row["status"] = "PRACTICE" if source == "practice" else ev["status"]
        if source != "practice":
            self.set_hist(h + [row])
            self.append_csv(row)
        self.debrief(row, ev, R, L, note)

    # ================================================================ DEBRIEF
    def debrief(self, row, ev, R, L, note):
        self.sfx("scan")
        scroll = 0
        while True:
            surf = pygame.Surface((self.w, 1500))
            surf.fill(BG)
            total = self._draw_debrief(surf, row, ev, R, L, note)
            view_h = self.h - HEADER_H
            scroll = max(0, min(scroll, max(0, total - view_h)))
            self.screen.fill(BG)
            self.screen.blit(surf, (0, HEADER_H - scroll))
            self.title, self.sub = "MISSION DEBRIEF", f"{row['crew']} · scan {row['session']}" + (" · PRACTICE (not saved)" if row["status"] == "PRACTICE" else "")
            self.header()
            if total > view_h and scroll < total - view_h - 4:
                self.text("scroll for more  v", (self.w - 20, self.h - 24), self.F_M, DIM, "midright")
            self.flip()
            for kind, a, _ in self.events():
                if kind == "key" and a in (pygame.K_RETURN, pygame.K_SPACE):
                    return
                if kind == "key" and a == pygame.K_ESCAPE:
                    self.audio.stop()
                    pygame.quit()
                    sys.exit()
                if kind == "key" and a in (pygame.K_DOWN, pygame.K_UP):
                    scroll += 80 if a == pygame.K_DOWN else -80
                if kind == "wheel":
                    scroll -= a * 60
                if kind == "click":
                    x, y = a[0], a[1] - HEADER_H + scroll
                    if self.new_btn.collidepoint((x, y)):
                        return

    def _draw_debrief(self, s, row, ev, R, L, note):
        x0 = max(30, (self.w - 1180) // 2)
        W = min(1180, self.w - 60)
        y = 20
        self.text("HEARING DEBRIEF", (x0, y + 6), self.F_M, MUTED, surf=s)
        self.new_btn = self.button("New scan  (ENTER)", (x0 + W - 110, y + 14), w=210, font=self.F_S, surf=s)
        y += 50
        if note:
            r = pygame.Rect(x0, y, W, 40)
            pygame.draw.rect(s, (40, 32, 8), r, border_radius=10)
            pygame.draw.rect(s, GOLD, r, 1, border_radius=10)
            self.text("> " + note, (r.x + 14, r.centery), self.F_BB, GOLD, "midleft", s)
            y += 52
        st = row["status"]
        col = STATUS_COL.get(st, MUTED)
        lines = self.wrap(ev["message"], self.F_B, W - 170)
        flag_lines = [f"{e} ear: {f}" for e, k in (("RIGHT", "R"), ("LEFT", "L")) for f in ev["flags"][k]] if int(row["valid"]) else []
        hgt = 116 + len(lines) * 28 + len(flag_lines) * 26 + len(ev["notes"]) * 24 + 40
        box = pygame.Rect(x0, y, W, hgt)
        self.panel(box, s, col, PANEL, 2)
        pygame.draw.circle(s, col, (box.x + 56, box.y + 60), 34)
        self.text(st, (box.x + 116, box.y + 16), self.F_H1, col, surf=s)
        yy = box.y + 70
        self.text(ev["headline"], (box.x + 116, yy), self.F_BB, TEXT, surf=s)
        yy += 34
        for l in lines:
            self.text(l, (box.x + 116, yy), self.F_B, TEXT, surf=s)
            yy += 28
        for f in flag_lines:
            self.text("> " + f, (box.x + 116, yy + 4), self.F_S, AMBER, surf=s)
            yy += 26
        for n in ev["notes"]:
            self.text("- " + n, (box.x + 116, yy + 4), self.F_S, MUTED, surf=s)
            yy += 24
        cc = {"HIGH": GREEN, "MEDIUM": AMBER, "LOW": RED}[ev["confidence"]]
        pill = pygame.Rect(box.x + 116, yy + 10, 170, 28)
        pygame.draw.rect(s, cc, pill, 2, border_radius=14)
        self.text("CONFIDENCE " + ev["confidence"], pill.center, self.F_M, cc, "center", s)
        self.text(ev["why"], (pill.right + 12, pill.centery), self.F_S, MUTED, "midleft", s)
        y = box.bottom + 18
        cw = (W - 18) // 2
        for i, (name, r, e) in enumerate((("RIGHT", R, "R"), ("LEFT", L, "L"))):
            card = pygame.Rect(x0 + i * (cw + 18), y, cw, 250)
            bad = not int(row["valid"])
            flagged = not bad and ev["flags"][e]
            c = MUTED if bad else RED if flagged else GREEN
            self.panel(card, s, LINE, PANEL)
            self.headphones((card.x + 80, card.y + 56), name.lower(), 0.5, s)
            self.text(f"{name} EAR", (card.x + 180, card.y + 22), self.F_M, MUTED, surf=s)
            tag = "UNRELIABLE" if bad else "CHANGED" if flagged else "NORMAL"
            tr = pygame.Rect(0, 0, self.F_M.size(tag)[0] + 24, 26)
            tr.topright = (card.right - 18, card.y + 18)
            pygame.draw.rect(s, c, tr, 2, border_radius=13)
            self.text(tag, tr.center, self.F_M, c, "center", s)
            v = r.get("srt")
            self.text(f"{v:+.1f} dB" if v is not None else "-", (card.x + 180, card.y + 44), self.F_MXL, TEXT, surf=s)
            b = ev["base"].get(f"srt_{e}") if ev["base"] else None
            self.meter(pygame.Rect(card.x + 24, card.y + 122, card.w - 48, 14), v, b, c, s)
            diff = None if (v is None or b is None) else v - b
            sub = (f"your normal {b:+.1f} dB · today {abs(diff):.1f} dB {'worse' if diff > 0 else 'better'}" if diff is not None and abs(diff) >= 0.5
                   else f"your normal {b:+.1f} dB · same as usual" if b is not None else "baseline forming")
            self.text(sub, (card.x + 24, card.y + 168), self.F_S, AMBER if (diff or 0) >= C["SRT_WORSE"] else MUTED, surf=s)
            self.text(f"decoded {r.get('codes_ok', 0)}/{C['TRIALS'] - 1} codes · {round((r.get('digit_acc') or 0) * 100)}% digits right",
                      (card.x + 24, card.y + 194), self.F_S, MUTED, surf=s)
            self.text("white = rough typical · gold = your normal", (card.x + 24, card.y + 220), self.F_M, DIM, surf=s)
        y += 268
        gp = pygame.Rect(x0, y, cw, 250)
        self.panel(gp, s, LINE, PANEL)
        self.text("LEFT VS RIGHT EAR", (gp.x + 20, gp.y + 18), self.F_M, MUTED, surf=s)
        self.text("Gap between ears", (gp.x + 20, gp.y + 52), self.F_B, surf=s)
        self.text(f"{row['ear_gap']} dB" if row.get("ear_gap") is not None else "-", (gp.right - 20, gp.y + 50), self.F_ML, TEXT, "topright", s)
        self.text("Hearing score (mean of both ears)", (gp.x + 20, gp.y + 96), self.F_B, surf=s)
        self.text(f"{row['hearing_score']} dB" if row.get("hearing_score") is not None else "-", (gp.right - 20, gp.y + 94), self.F_ML, TEXT, "topright", s)
        self.para("Why it matters: volume, headphones and room noise affect BOTH ears. If only ONE ear changes, it's probably the ear itself.",
                  (gp.x + 20, gp.y + 146), gp.w - 40, self.F_S, MUTED, 4, s)
        tp = pygame.Rect(x0 + cw + 18, y, cw, 250)
        self.panel(tp, s, LINE, PANEL)
        self.text("TREND", (tp.x + 20, tp.y + 18), self.F_M, MUTED, surf=s)
        self._trend(s, pygame.Rect(tp.x + 20, tp.y + 44, tp.w - 40, 190), self.hist() or [row])
        y += 268
        ex = pygame.Rect(x0, y, W, 96)
        self.panel(ex, s, LINE, PANEL)
        self.text("EXPORT FOR MISSION PULSE", (ex.x + 20, ex.y + 16), self.F_M, MUTED, surf=s)
        self.text("Saved automatically to commscheck_scans.csv (next to this program)" if row["status"] != "PRACTICE"
                  else "Practice scan: not saved", (ex.x + 20, ex.y + 44), self.F_B, surf=s)
        self.text("hearing_score = mean speech-in-noise score of both ears (dB, lower = better)", (ex.x + 20, ex.y + 70), self.F_S, MUTED, surf=s)
        return y + 120

    def _trend(self, s, rect, rows):
        rows = rows[-12:]
        if len(rows) < 2:
            self.text("Do at least 2 scans to see your trend.", rect.center, self.F_S, DIM, "center", s)
            return
        vals = [v for r in rows for v in (core._num(r.get("srt_R")), core._num(r.get("srt_L"))) if v is not None]
        lo, hi = min(vals) - 1, max(vals) + 1
        L, T, B = rect.x + 44, rect.y + 22, rect.bottom - 22
        X = lambda i: L + i * (rect.right - 10 - L) / (len(rows) - 1)
        Y = lambda v: T + (v - lo) * (B - T) / ((hi - lo) or 1)          # lower dB (better) drawn HIGHER
        self.text("SPEECH IN NOISE (dB) · higher on chart = better", (rect.x, rect.y), self.F_M, MUTED, surf=s)
        for k in range(3):
            v = lo + (hi - lo) * k / 2
            pygame.draw.line(s, (27, 40, 70), (L, Y(v)), (rect.right - 10, Y(v)))
            self.text(f"{v:+.0f}", (L - 6, Y(v)), self.F_M, DIM, "midright", s)
        for key, c in (("srt_R", ORANGE), ("srt_L", BLUE)):
            pts = [(X(i), Y(core._num(r.get(key))), r) for i, r in enumerate(rows) if core._num(r.get(key)) is not None]
            if len(pts) > 1:
                pygame.draw.lines(s, c, False, [(int(x), int(y)) for x, y, _ in pts], 3)
            for x, y, r in pts:
                if r.get("data_source") == "simulated":
                    pygame.draw.circle(s, BG, (int(x), int(y)), 5)
                    pygame.draw.circle(s, c, (int(x), int(y)), 5, 2)
                else:
                    pygame.draw.circle(s, c, (int(x), int(y)), 5)
        self.text("o right ear", (rect.x, rect.bottom - 4), self.F_M, ORANGE, surf=s)
        self.text("o left ear", (rect.x + 120, rect.bottom - 4), self.F_M, BLUE, surf=s)
        self.text("hollow = simulated", (rect.x + 230, rect.bottom - 4), self.F_M, DIM, surf=s)

    # ================================================================ MAIN
    def run(self):
        msg = ("", TEXT)
        while True:
            choice = self.home(msg)
            msg = ("", TEXT)
            try:
                if choice == "start":
                    self.run_scan()
                else:
                    self.run_demo()
            except Abort:
                self.audio.stop()
                self.progress = None
                msg = ("Scan aborted. Nothing saved.", AMBER)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="COMMS CHECK hearing-in-noise game")
    ap.add_argument("--windowed", action="store_true", help="1280x800 window instead of full screen")
    ap.add_argument("--rebuild-voice", action="store_true", help="regenerate the computer voice in comms_voice/")
    a = ap.parse_args()
    App(windowed=a.windowed, rebuild_voice=a.rebuild_voice).run()
