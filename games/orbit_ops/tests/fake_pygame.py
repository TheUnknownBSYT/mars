"""
A tiny stand-in for pygame used ONLY by tests/smoke_test.py, so the full game
flow can be exercised on a machine without a display or pygame installed.
Draw calls do nothing; Rect geometry and events behave like pygame.
"""
import sys
import time as _time
import types

pg = types.ModuleType("pygame")

# ---------------------------------------------------------------- constants
pg.QUIT, pg.KEYDOWN, pg.KEYUP = 256, 768, 769
pg.SRCALPHA, pg.SCALED, pg.BLEND_RGBA_MIN = 65536, 512, 20
_keys = ["ESCAPE", "SPACE", "RETURN", "KP_ENTER", "UP", "DOWN", "LEFT", "RIGHT", "TAB", "BACKSPACE",
         "F2", "F3", "F11", "f", "j", "m", "p", "q", "t"]
for i, k in enumerate(_keys):
    setattr(pg, "K_" + k, 1000 + i)


# ---------------------------------------------------------------- Rect
class Rect:
    def __init__(self, *a):
        if len(a) == 1:
            a = tuple(a[0]) if not isinstance(a[0], Rect) else (a[0].x, a[0].y, a[0].w, a[0].h)
        if len(a) == 2:
            a = (*a[0], *a[1])
        self.x, self.y, self.w, self.h = (int(v) for v in a)

    width = property(lambda s: s.w, lambda s, v: setattr(s, "w", int(v)))
    height = property(lambda s: s.h, lambda s, v: setattr(s, "h", int(v)))
    left = property(lambda s: s.x, lambda s, v: setattr(s, "x", int(v)))
    top = property(lambda s: s.y, lambda s, v: setattr(s, "y", int(v)))
    right = property(lambda s: s.x + s.w, lambda s, v: setattr(s, "x", int(v) - s.w))
    bottom = property(lambda s: s.y + s.h, lambda s, v: setattr(s, "y", int(v) - s.h))
    centerx = property(lambda s: s.x + s.w // 2, lambda s, v: setattr(s, "x", int(v) - s.w // 2))
    centery = property(lambda s: s.y + s.h // 2, lambda s, v: setattr(s, "y", int(v) - s.h // 2))
    size = property(lambda s: (s.w, s.h))
    topleft = property(lambda s: (s.x, s.y), lambda s, v: (setattr(s, "left", v[0]), setattr(s, "top", v[1])))
    topright = property(lambda s: (s.right, s.y), lambda s, v: (setattr(s, "right", v[0]), setattr(s, "top", v[1])))
    midtop = property(lambda s: (s.centerx, s.y), lambda s, v: (setattr(s, "centerx", v[0]), setattr(s, "top", v[1])))
    midleft = property(lambda s: (s.x, s.centery), lambda s, v: (setattr(s, "left", v[0]), setattr(s, "centery", v[1])))
    midright = property(lambda s: (s.right, s.centery), lambda s, v: (setattr(s, "right", v[0]), setattr(s, "centery", v[1])))
    center = property(lambda s: (s.centerx, s.centery), lambda s, v: (setattr(s, "centerx", v[0]), setattr(s, "centery", v[1])))

    def inflate(self, dx, dy):
        return Rect(self.x - dx // 2, self.y - dy // 2, self.w + dx, self.h + dy)


pg.Rect = Rect


# ---------------------------------------------------------------- Surface
class Surface:
    def __init__(self, size, flags=0):
        self._size = (int(size[0]), int(size[1]))

    def fill(self, *a, **k):
        pass

    def blit(self, src, dest, *a, **k):
        if isinstance(dest, Rect):
            return dest
        return Rect(dest[0], dest[1], *src._size)

    def get_rect(self, **kw):
        r = Rect(0, 0, *self._size)
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    def get_size(self):
        return self._size


pg.Surface = Surface


def _check_color(c):
    assert len(c) in (3, 4) and all(0 <= int(v) <= 255 for v in c), f"bad colour {c}"


def _check_pts(pts):
    for p in pts:
        assert len(p) == 2 and all(isinstance(v, (int, float)) for v in p), f"bad point {p}"


draw = types.ModuleType("pygame.draw")
draw.rect = lambda s, c, r, *a, **k: (_check_color(c), Rect(r) if not isinstance(r, Rect) else r)[1]
draw.circle = lambda s, c, p, r, *a, **k: (_check_color(c), _check_pts([p]))
draw.polygon = lambda s, c, pts, *a, **k: (_check_color(c), _check_pts(pts))
draw.line = lambda s, c, a, b, *x, **k: (_check_color(c), _check_pts([a, b]))
draw.lines = lambda s, c, closed, pts, *a, **k: (_check_color(c), _check_pts(pts), len(pts) >= 2 or (_ for _ in ()).throw(AssertionError("lines needs 2 pts")))
draw.ellipse = lambda s, c, r, *a, **k: _check_color(c)
pg.draw = draw


# ---------------------------------------------------------------- font
class _Font:
    def __init__(self, *a, **k):
        self.sz = a[1] if len(a) > 1 else 20

    def render(self, text, aa, color, *a):
        _check_color(color)
        assert isinstance(text, str)
        return Surface((len(text) * self.sz * 0.5, self.sz))

    def size(self, text):
        return (int(len(text) * self.sz * 0.5), self.sz)

    def set_bold(self, b):
        pass


font = types.ModuleType("pygame.font")
font.Font = _Font
font.SysFont = lambda name, size, bold=False, italic=False: _Font(None, size)
pg.font = font


# ---------------------------------------------------------------- display / time / mixer / event
display = types.ModuleType("pygame.display")
display.set_mode = lambda size, flags=0: Surface(size)
display.set_caption = lambda *a: None
display.flip = lambda: None
display.toggle_fullscreen = lambda: None
pg.display = display


class Clock:
    def tick(self, fps=0):
        _time.sleep(0.001)
        return 1

    tick_busy_loop = tick


ptime = types.ModuleType("pygame.time")
ptime.Clock = Clock
pg.time = ptime

mixer = types.ModuleType("pygame.mixer")
mixer.pre_init = lambda *a, **k: None
mixer.init = lambda *a, **k: None
mixer.get_init = lambda: (44100, -16, 1)


class Sound:
    def __init__(self, buffer=None):
        assert buffer is not None

    def play(self):
        pass


mixer.Sound = Sound
pg.mixer = mixer

event = types.ModuleType("pygame.event")
QUEUE = []
event.get = lambda: [QUEUE.pop(0) for _ in range(len(QUEUE))]
pg.event = event


class Event:
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)


pg.event.Event = Event
pg.init = lambda: None
pg.quit = lambda: None


def install():
    sys.modules["pygame"] = pg
    for name in ("draw", "font", "display", "time", "mixer", "event"):
        sys.modules["pygame." + name] = getattr(pg, name)
    return pg
