"""
Builds the list of trials for each round BEFORE the round starts.

Everything random (waiting times, which object appears, when rules change)
is decided here, so the game scenes only have to play the list back.
Pure Python: no pygame, so it can be unit-tested.
"""
import random

import config as C


def build_round1(rng: random.Random, n: int = C.R1_TRIALS):
    """Master Alarm: n trials, each with a random wait (ISI)."""
    return [
        {"round": 1, "trial": i + 1, "condition": "alarm",
         "isi_s": rng.uniform(*C.R1_ISI_S), "slot": rng.randrange(3)}
        for i in range(n)
    ]


def build_round2(rng: random.Random, n: int = C.R2_TRIALS, n_go: int = C.R2_GO_TRIALS):
    """Debris Watch: go (debris) and no-go (satellite) trials, shuffled.

    No more than 3 satellites in a row, so the round never feels 'empty'.
    """
    n_go = min(n_go, n)
    while True:
        kinds = ["debris"] * n_go + ["satellite"] * (n - n_go)
        rng.shuffle(kinds)
        run, ok = 0, True
        for k in kinds:
            run = run + 1 if k == "satellite" else 0
            if run > 3:
                ok = False
                break
        if ok:
            break
    return [
        {"round": 2, "trial": i + 1, "condition": "go" if k == "debris" else "no_go",
         "stimulus": k, "isi_s": rng.uniform(*C.R2_ISI_S), "seed": rng.randrange(10**6)}
        for i, k in enumerate(kinds)
    ]


def correct_key_r3(rule: str, shape: str, color: str) -> str:
    """Which thruster ('left' / 'right') is correct for this object under this rule."""
    return C.R3_SHAPE_MAP[shape] if rule == "shape" else C.R3_COLOR_MAP[color]


def build_round3(rng: random.Random, n: int = C.R3_TRIALS):
    """Mission Control Orders: rule blocks of 3-5 trials that alternate SHAPE / COLOR.

    Incongruent objects (shape and colour point to different keys) let us detect
    'old-rule' errors; about a third are congruent for variety.
    """
    rules = []
    rule = rng.choice(["shape", "color"])
    while len(rules) < n:
        for _ in range(rng.randint(*C.R3_BLOCK_LEN)):
            if len(rules) < n:
                rules.append(rule)
        rule = "color" if rule == "shape" else "shape"

    shapes = list(C.R3_SHAPE_MAP)
    colors = list(C.R3_COLOR_MAP)
    trials = []
    for i, rule in enumerate(rules):
        congruent = rng.random() < C.R3_CONGRUENT_SHARE
        shape = rng.choice(shapes)
        # pick the colour that agrees / disagrees with the shape's key
        same = [c for c in colors if C.R3_COLOR_MAP[c] == C.R3_SHAPE_MAP[shape]]
        diff = [c for c in colors if C.R3_COLOR_MAP[c] != C.R3_SHAPE_MAP[shape]]
        color = rng.choice(same if congruent else diff)
        trials.append({
            "round": 3, "trial": i + 1,
            "rule": rule,
            "is_switch": int(i > 0 and rule != rules[i - 1]),
            "is_first": int(i == 0),
            "condition": ("switch" if i > 0 and rule != rules[i - 1] else ("first" if i == 0 else "repeat")),
            "congruent": int(congruent),
            "shape": shape, "color": color,
            "stimulus": f"{color}_{shape}",
            "correct_key": correct_key_r3(rule, shape, color),
            "isi_s": rng.uniform(*C.R3_ISI_S),
        })
    return trials
