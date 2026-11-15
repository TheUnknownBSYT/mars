"""
ORBIT OPS - Mission Pulse reaction-time game.

Run:   python main.py
       python main.py --crew AST-02          (start with a crew ID)
       python main.py --demo AST-01          (create 8 SIMULATED sessions, then start)

Keys:  F11 fullscreen   M mute   ESC back / pause / quit
"""
import argparse
import sys
import time

import pygame

import config as C
from core import logger
from game import gfx
from game.audio import Audio
from game.screens import CheckinScene


class App:
    def __init__(self, crew="AST-01"):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("ORBIT OPS - Mission Pulse reaction-time check")
        self.screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT), pygame.SCALED)
        self.clock = pygame.time.Clock()
        self.audio = Audio()
        self.stars = gfx.Starfield()
        self.crew = crew
        self.session = None
        self.running = True
        self.scene = CheckinScene(self)

    def go(self, scene):
        self.scene = scene
        scene.redraw = True

    def run(self):
        last = time.perf_counter()
        last_draw = 0.0
        while self.running:
            scene = self.scene
            # Reaction-time rounds: busy-wait loop (~1 ms polling) for accurate key times.
            if scene.precise:
                self.clock.tick_busy_loop(C.FPS_PRECISE)
            else:
                self.clock.tick(C.FPS_MENU)

            now = time.perf_counter()          # time stamp for every key read this pass
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_m and not self._typing():
                    self.audio.toggle_mute()
                else:
                    self.scene.handle(e, now)

            dt = now - last
            last = now
            self.scene.update(now, dt)

            # Draw at ~60 fps, or immediately when a scene asks (e.g. stimulus appears)
            scene = self.scene
            if scene.redraw or now - last_draw >= 1 / 60:
                scene.draw(self.screen, now)
                pygame.display.flip()
                scene.on_flip(time.perf_counter())   # stimulus onset = this moment
                scene.redraw = False
                last_draw = now
        pygame.quit()

    def _typing(self):
        """M key types a letter while editing the crew ID, so don't treat it as mute there."""
        return isinstance(self.scene, CheckinScene) and self.scene.sel == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="ORBIT OPS reaction-time game")
    ap.add_argument("--crew", default="AST-01", help="crew ID to start with")
    ap.add_argument("--demo", metavar="CREW", help="create 8 SIMULATED sessions for CREW first")
    args = ap.parse_args(argv)
    crew = args.crew
    if args.demo:
        crew = args.demo.upper()
        logger.make_demo_history(crew)
        print(f"Created 8 simulated sessions for {crew} in {C.SESSIONS_CSV}")
    App(crew).run()


if __name__ == "__main__":
    sys.exit(main())
