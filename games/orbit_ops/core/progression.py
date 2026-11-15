"""
Ranks, badges and station modules - rewards for CONSISTENCY, never for raw speed,
so a slow (tired) day is never punished.
Pure Python: no pygame.
"""
import json
from datetime import date

import config as C

BADGES = {
    "first_docking":   ("First Docking",     "Completed your first mission check"),
    "zero_lapses":     ("Zero Lapses",       "No lapses in Master Alarm"),
    "no_false_starts": ("Patient Pilot",     "No false starts in Master Alarm"),
    "perfect_hold":    ("Perfect Hold Fire", "Never shot a friendly satellite"),
    "quick_adapter":   ("Quick Adapter",     "95%+ correct on Mission Control orders"),
    "steady_hands":    ("Steady Hands",      "Very consistent reaction times"),
    "streak_3":        ("3-Day Streak",      "Checked in 3 days in a row"),
    "streak_7":        ("7-Day Streak",      "Checked in 7 days in a row"),
}


def _load():
    try:
        return json.loads(C.PROGRESS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data):
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    C.PROGRESS_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")


def rank_for(sessions_done):
    title = C.RANKS[0][1]
    for need, name in C.RANKS:
        if sessions_done >= need:
            title = name
    nxt = next(((need, name) for need, name in C.RANKS if need > sessions_done), None)
    return title, nxt


def modules_for(sessions_done):
    k = min(len(C.STATION_MODULES), 1 + sessions_done // C.MODULE_EVERY)
    return C.STATION_MODULES[:k]


def day_streak(day_list):
    """Consecutive days (ending today or on the latest day) with at least one session."""
    days = sorted({d for d in day_list})
    if not days:
        return 0
    streak, cur = 1, days[-1]
    for d in reversed(days[:-1]):
        if (cur - d).days == 1:
            streak += 1
            cur = d
        elif (cur - d).days > 1:
            break
    return streak


def update(astronaut, scores, history_rows, today=None):
    """Call after a saved session. Returns dict with rank, modules, new badges, streak."""
    today = today or date.today()
    data = _load()
    me = data.setdefault(astronaut, {"badges": []})
    days = []
    for r in history_rows:
        try:
            days.append(date.fromisoformat(str(r.get("timestamp", ""))[:10]))
        except ValueError:
            pass
    days.append(today)
    streak = day_streak(days)
    done = len(history_rows) + 1

    earned = []

    def give(key, cond):
        if cond and key not in me["badges"]:
            me["badges"].append(key)
            earned.append(key)

    s = scores
    give("first_docking", True)
    give("zero_lapses", s.get("r1_lapses") == 0)
    give("no_false_starts", s.get("r1_false_starts") == 0)
    give("perfect_hold", s.get("r2_false_alarms") == 0)
    give("quick_adapter", (s.get("r3_accuracy") or 0) >= 0.95)
    give("steady_hands", s.get("r1_sd_ms") is not None and s["r1_sd_ms"] <= 35)
    give("streak_3", streak >= 3)
    give("streak_7", streak >= 7)

    before_modules = modules_for(done - 1)
    after_modules = modules_for(done)
    _save(data)
    title, nxt = rank_for(done)
    return {
        "sessions_done": done, "rank": title, "next_rank": nxt, "streak": streak,
        "new_badges": [BADGES[k] for k in earned],
        "all_badges": [BADGES[k] for k in me["badges"] if k in BADGES],
        "modules": after_modules,
        "new_module": after_modules[-1] if len(after_modules) > len(before_modules) else None,
    }
