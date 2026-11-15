"""
Sound effects, generated in code (no audio files needed).

IMPORTANT for the science: sounds are played only AFTER a response
(feedback), never at the moment a stimulus appears. Reaction time stays a
purely visual measure, the same as NASA's PVT, and sound-card delay cannot
change the numbers.
"""
import math
import random
from array import array

import pygame

RATE = 44100


class Audio:
    def __init__(self):
        self.ok = False
        self.muted = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            freq, _, channels = pygame.mixer.get_init()
            self.rate, self.channels = freq, channels
            self._build()
            self.ok = True
        except Exception:      # no audio device -> play silently
            self.ok = False

    # ---- synthesis helpers
    def _make(self, samples):
        data = array("h")
        for v in samples:
            v = max(-1.0, min(1.0, v))
            iv = int(v * 32000)
            for _ in range(self.channels):
                data.append(iv)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _tone(self, f0, f1, dur, vol=0.4, wave="sine", noise=0.0, decay=4.0):
        n = int(self.rate * dur)
        out, phase = [], 0.0
        rng = random.Random(1)
        for i in range(n):
            t = i / n
            f = f0 + (f1 - f0) * t
            phase += math.tau * f / self.rate
            s = math.sin(phase)
            if wave == "square":
                s = 1.0 if s >= 0 else -1.0
            s = s * (1 - noise) + rng.uniform(-1, 1) * noise
            env = min(1.0, i / (self.rate * 0.005)) * math.exp(-decay * t)
            out.append(s * env * vol)
        return out

    def _build(self):
        T = self._tone
        self.sounds = {
            "hit": self._make(T(1250, 1250, .07, .30)),
            "lapse": self._make(T(700, 600, .12, .28)),
            "error": self._make(T(170, 140, .22, .35, "square", decay=3)),
            "laser": self._make(T(1600, 300, .16, .30, "square", decay=5)),
            "boom": self._make(T(120, 60, .30, .45, noise=.85, decay=6)),
            "safe": self._make(T(880, 880, .08, .25) + T(1320, 1320, .10, .25)),
            "thruster": self._make(T(220, 180, .10, .25, noise=.6)),
            "radio": self._make(T(1000, 1000, .05, .2) + T(300, 300, .25, .25, noise=.9, decay=2) + T(1000, 1000, .05, .2)),
            "chime": self._make(T(660, 660, .12, .25) + T(990, 990, .18, .25)),
            "dock": self._make(T(330, 990, .6, .3, decay=1.5)),
            "tick": self._make(T(1500, 1500, .02, .15)),
        }

    def play(self, name):
        if self.ok and not self.muted and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted
