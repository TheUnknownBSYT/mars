"""Fresh content every shift (nothing repeats). Pure Python, seeded RNG."""
import math
import random

import config as C


def _arena(pad=40):
    x, y, w, h = C.ARENA
    return x + pad, y + pad, x + w - pad, y + h - pad


# ---------------------------------------------------------------- Task 1
def port_rounds(rng: random.Random, n=None):
    n = C.T1_ROUNDS if n is None else n
    x0, y0, x1, y1 = _arena(50)
    rounds = []
    for i in range(n):
        pts = []
        while len(pts) < C.T1_PORTS:
            p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= C.T1_MIN_GAP for q in pts):
                pts.append(p)
        rounds.append({"round": i + 1, "ports": pts})          # ports[k] has number k+1
    return rounds


# ---------------------------------------------------------------- Task 2
def track_rounds(rng: random.Random, n=None):
    n = C.T2_ROUNDS if n is None else n
    x0, y0, x1, y1 = _arena(40)
    rounds = []
    for i in range(n):
        sats = []
        while len(sats) < C.T2_SATELLITES:
            p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
            if all(math.hypot(p[0] - s[0], p[1] - s[1]) > 90 for s in sats):
                sats.append(p)
        heads = [rng.uniform(0, math.tau) for _ in sats]
        turns = [rng.uniform(-1.2, 1.2) for _ in sats]       # rad/s gentle curving
        tagged = rng.sample(range(C.T2_SATELLITES), C.T2_TAGGED)
        rounds.append({"round": i + 1, "start": sats, "heading": heads, "turn": turns, "tagged": sorted(tagged),
                       "seed": rng.randrange(10**6)})
    return rounds


def simulate_track(rnd, t):
    """Positions of all satellites t seconds after movement starts (deterministic)."""
    x0, y0, x1, y1 = _arena(40)
    rng = random.Random(rnd["seed"])
    pos = [list(p) for p in rnd["start"]]
    head = list(rnd["heading"])
    turn = list(rnd["turn"])
    dt = 1 / 60
    steps = int(t / dt)
    for k in range(steps):
        for j in range(len(pos)):
            if k % 60 == 0:
                turn[j] = max(-1.5, min(1.5, turn[j] + rng.uniform(-0.6, 0.6)))
            head[j] += turn[j] * dt
            pos[j][0] += math.cos(head[j]) * C.T2_SPEED * dt
            pos[j][1] += math.sin(head[j]) * C.T2_SPEED * dt
            if pos[j][0] < x0 or pos[j][0] > x1:
                head[j] = math.pi - head[j]
                pos[j][0] = min(max(pos[j][0], x0), x1)
            if pos[j][1] < y0 or pos[j][1] > y1:
                head[j] = -head[j]
                pos[j][1] = min(max(pos[j][1], y0), y1)
    return [tuple(p) for p in pos]


# ---------------------------------------------------------------- Task 3
def beam_rounds(rng: random.Random, n=None):
    n = C.T3_ROUNDS if n is None else n
    rounds = []
    for i in range(n):
        # smooth path = sum of sines with random phases (different every time, same difficulty)
        comps = [(rng.uniform(0.08, 0.14), rng.uniform(0, math.tau)), (rng.uniform(0.18, 0.26), rng.uniform(0, math.tau)),
                 (rng.uniform(0.07, 0.12), rng.uniform(0, math.tau)), (rng.uniform(0.15, 0.22), rng.uniform(0, math.tau))]
        total = rng.randint(*C.T3_FLASHES)
        greens = rng.randint(*C.T3_GREEN)
        greens = min(greens, total)
        colors = ["green"] * greens + ["red"] * (total - greens)
        rng.shuffle(colors)
        # flash times spread across the round with a minimum gap
        span = C.T3_DURATION_S - 2.5
        times = sorted(rng.uniform(1.5, 1.5 + span) for _ in range(total))
        for k in range(1, len(times)):
            times[k] = max(times[k], times[k - 1] + C.T3_FLASH_GAP_S)
        times = [t for t in times if t < C.T3_DURATION_S - 0.8]
        colors = colors[:len(times)]
        x, y, w, h = C.ARENA
        edges = []
        for _ in times:
            side = rng.choice(["top", "bottom", "left", "right"])
            if side == "top":
                edges.append((rng.uniform(x + 40, x + w - 40), y + 14))
            elif side == "bottom":
                edges.append((rng.uniform(x + 40, x + w - 40), y + h - 14))
            elif side == "left":
                edges.append((x + 14, rng.uniform(y + 40, y + h - 40)))
            else:
                edges.append((x + w - 14, rng.uniform(y + 40, y + h - 40)))
        rounds.append({"round": i + 1, "path": comps, "flashes": list(zip(times, colors, edges)),
                       "greens": colors.count("green")})
    return rounds


def beam_position(rnd, t):
    x, y, w, h = C.ARENA
    (fx1, px1), (fx2, px2), (fy1, py1), (fy2, py2) = rnd["path"]
    cx, cy = x + w / 2, y + h / 2
    ax, ay = w / 2 - 90, h / 2 - 80
    px = cx + ax * (0.65 * math.sin(math.tau * fx1 * t + px1) + 0.35 * math.sin(math.tau * fx2 * t + px2))
    py = cy + ay * (0.65 * math.sin(math.tau * fy1 * t + py1) + 0.35 * math.sin(math.tau * fy2 * t + py2))
    return px, py


def track_frames(rnd, fps=60):
    """All satellite positions for every frame of the movement phase (precomputed once per round)."""
    x0, y0, x1, y1 = _arena(40)
    rng = random.Random(rnd["seed"])
    pos = [list(p) for p in rnd["start"]]
    head = list(rnd["heading"])
    turn = list(rnd["turn"])
    dt = 1 / fps
    frames = [[tuple(p) for p in pos]]
    for k in range(int(C.T2_MOVE_S * fps)):
        for j in range(len(pos)):
            if k % 60 == 0:
                turn[j] = max(-1.5, min(1.5, turn[j] + rng.uniform(-0.6, 0.6)))
            head[j] += turn[j] * dt
            pos[j][0] += math.cos(head[j]) * C.T2_SPEED * dt
            pos[j][1] += math.sin(head[j]) * C.T2_SPEED * dt
            if pos[j][0] < x0 or pos[j][0] > x1:
                head[j] = math.pi - head[j]
                pos[j][0] = min(max(pos[j][0], x0), x1)
            if pos[j][1] < y0 or pos[j][1] > y1:
                head[j] = -head[j]
                pos[j][1] = min(max(pos[j][1], y0), y1)
        frames.append([tuple(p) for p in pos])
    return frames
