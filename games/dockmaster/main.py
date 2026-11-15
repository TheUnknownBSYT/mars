"""
DOCKMASTER - 3-minute hand-eye + memory check
Port Sequence · Track the Satellite · Steady Beam (Mission Pulse).

Run:   python main.py
       python main.py --crew AST-02
       python main.py --demo AST-01      (8 SIMULATED shifts first, for demos)
Keys:  F11 fullscreen · M mute · ESC pause/back/quit
"""
import argparse
import sys
import time

import pygame

import config as C
from core import logger
from game.audio import Audio
from game.screens import CheckinScene


class App:
    def __init__(self, crew="AST-01"):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("DOCKMASTER - 3-minute hand-eye + memory check")
        self.screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT), pygame.SCALED)
        self.clock = pygame.time.Clock()
        self.audio = Audio()
        self.crew = crew
        self.session = None
        self.running = True
        self.mouse = (C.WIDTH // 2, C.HEIGHT // 2)
        self.scene = CheckinScene(self)

    def go(self, scene):
        self.scene = scene

    def set_mouse(self, pos):
        """Move the hand controller (mouse) so steering starts without a jump."""
        p = (int(pos[0]), int(pos[1]))
        try:
            pygame.mouse.set_pos(p)
        except Exception:
            pass
        self.mouse = p

    def run(self):
        last = time.perf_counter()
        while self.running:
            self.clock.tick(C.FPS)
            now = time.perf_counter()
            self.mouse = pygame.mouse.get_pos()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_m and not (isinstance(self.scene, CheckinScene) and self.scene.sel == 0):
                    self.audio.toggle_mute()
                else:
                    self.scene.handle(e, now)
            dt, last = now - last, now
            self.scene.update(now, dt)
            self.scene.draw(self.screen, now)
            pygame.display.flip()
        pygame.quit()


def main(argv=None):
    ap = argparse.ArgumentParser(description="DOCKMASTER readiness check")
    ap.add_argument("--crew", default="AST-01")
    ap.add_argument("--demo", metavar="CREW", help="create 8 SIMULATED shifts for CREW first")
    a = ap.parse_args(argv)
    crew = a.crew
    if a.demo:
        crew = a.demo.upper()
        logger.make_demo_history(crew)
        print(f"Created 8 simulated shifts for {crew} in {C.SESSIONS_CSV}")
    App(crew).run()


if __name__ == "__main__":
    sys.exit(main())
