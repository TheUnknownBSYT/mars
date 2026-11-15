"""
pygame stand-in that renders with Pillow, so the game's real drawing code can
produce screenshots on a machine without a display. Used by tests/screenshots.py.
"""
from PIL import Image, ImageChops, ImageDraw, ImageFont

import fake_pygame

pg = fake_pygame.pg
Rect = fake_pygame.Rect
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def _c(color, alpha_ok):
    c = tuple(int(v) for v in color)
    if len(c) == 3:
        c = c + (255,)
    return c if alpha_ok else c[:3] + (255,)


class Surface:
    def __init__(self, size, flags=0, img=None):
        self.alpha = bool(flags & pg.SRCALPHA) or img is not None
        self.img = img if img is not None else Image.new("RGBA", (int(size[0]), int(size[1])),
                                                         (0, 0, 0, 0) if self.alpha else (0, 0, 0, 255))
        self._size = self.img.size

    def fill(self, color, *a, **k):
        self.img.paste(_c(color, self.alpha), (0, 0, *self._size))

    def blit(self, src, dest, area=None, special_flags=0):
        x, y = (dest.x, dest.y) if isinstance(dest, Rect) else (int(dest[0]), int(dest[1]))
        if special_flags == pg.BLEND_RGBA_MIN:
            region = self.img.crop((x, y, x + src._size[0], y + src._size[1]))
            self.img.paste(ImageChops.darker(region, src.img), (x, y))
        else:
            layer = Image.new("RGBA", self._size, (0, 0, 0, 0))
            layer.paste(src.img, (x, y))
            self.img = Image.alpha_composite(self.img, layer)
        return Rect(x, y, *src._size)

    def get_rect(self, **kw):
        r = Rect(0, 0, *self._size)
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    def get_size(self):
        return self._size

    @property
    def d(self):
        return ImageDraw.Draw(self.img)


def _rect(s, color, r, width=0, border_radius=0, **k):
    r = r if isinstance(r, Rect) else Rect(r)
    if r.w <= 0 or r.h <= 0:
        return r
    box = [r.x, r.y, r.x + r.w - 1, r.y + r.h - 1]
    col = _c(color, s.alpha)
    rad = max(0, min(int(border_radius), r.w // 2, r.h // 2))
    if width:
        s.d.rounded_rectangle(box, rad, outline=col, width=int(width))
    else:
        s.d.rounded_rectangle(box, rad, fill=col)
    return r


def _circle(s, color, center, radius, width=0, **k):
    x, y, r = center[0], center[1], float(radius)
    if r <= 0:
        return
    box = [x - r, y - r, x + r, y + r]
    col = _c(color, s.alpha)
    if width:
        s.d.ellipse(box, outline=col, width=int(width))
    else:
        s.d.ellipse(box, fill=col)


def _polygon(s, color, pts, width=0, **k):
    pts = [tuple(map(float, p)) for p in pts]
    col = _c(color, s.alpha)
    if width:
        s.d.line(pts + [pts[0]], fill=col, width=int(width), joint="curve")
    else:
        s.d.polygon(pts, fill=col)


def _line(s, color, a, b, width=1, **k):
    s.d.line([tuple(a), tuple(b)], fill=_c(color, s.alpha), width=int(width))


def _lines(s, color, closed, pts, width=1, **k):
    pts = [tuple(p) for p in pts] + ([tuple(pts[0])] if closed else [])
    s.d.line(pts, fill=_c(color, s.alpha), width=int(width), joint="curve")


def _ellipse(s, color, r, width=0, **k):
    r = r if isinstance(r, Rect) else Rect(r)
    box = [r.x, r.y, r.x + r.w, r.y + r.h]
    col = _c(color, s.alpha)
    if width:
        s.d.ellipse(box, outline=col, width=int(width))
    else:
        s.d.ellipse(box, fill=col)


class Font:
    def __init__(self, name, size, bold=False, mono=False):
        self.size_px = size
        self.mono = mono
        self.bold = bold
        self._load()

    def _load(self):
        path = (FONT_MONO_B if self.bold else FONT_MONO) if self.mono else (FONT_BOLD if self.bold else FONT_REG)
        self.f = ImageFont.truetype(path, max(6, int(self.size_px * (0.62 if self.mono else 0.62))))

    def set_bold(self, b):
        self.bold = b
        self._load()

    def size(self, text):
        b = self.f.getbbox(text or " ")
        return (b[2], int(self.size_px * 0.8))

    def render(self, text, aa, color, *a):
        w, h = self.size(text)
        img = Image.new("RGBA", (max(1, w + 2), max(1, h)), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((0, (h - self.f.size) / 2 - 1), text, font=self.f, fill=_c(color, True))
        return Surface(None, img=img)


def install():
    pg = fake_pygame.install()
    pg.Surface = Surface
    pg.draw.rect, pg.draw.circle, pg.draw.polygon = _rect, _circle, _polygon
    pg.draw.line, pg.draw.lines, pg.draw.ellipse = _line, _lines, _ellipse
    pg.font.Font = lambda name, size: Font(name, size)
    pg.font.SysFont = lambda name, size, bold=False, italic=False: Font(name, int(size * 1.25), bold, mono=True)
    pg.display.set_mode = lambda size, flags=0: Surface(size)
    return pg
