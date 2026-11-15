"""
DOCKMASTER - all settings in one place.
Three 1-minute tasks (~3 min total): Port Sequence, Track the Satellite, Steady Beam.
Change numbers here only, so every shift uses identical rules.
"""
from pathlib import Path

TASK_VERSION = "dockmaster-py-1.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_CSV = DATA_DIR / "sessions.csv"
EVENTS_CSV = DATA_DIR / "events.csv"

WIDTH, HEIGHT = 1280, 720
FPS = 120
ARENA = (230, 110, 820, 540)          # x, y, w, h - play area for all tasks

# ------------------------------------------------ Task 1: PORT SEQUENCE
T1_ROUNDS = 5
T1_PORTS = 5                          # numbers 1..5
T1_SHOW_S = 1.5                       # numbers visible
T1_PORT_RADIUS = 28
T1_MIN_GAP = 115                      # min distance between ports (px)
T1_ROUND_TIMEOUT_S = 10.0
T1_FEEDBACK_S = 0.9

# ------------------------------------------------ Task 2: TRACK THE SATELLITE
T2_ROUNDS = 4
T2_SATELLITES = 6
T2_TAGGED = 2
T2_BLINK_S = 2.0
T2_MOVE_S = 6.0
T2_SPEED = 150                        # px/s
T2_RADIUS = 22
T2_ANSWER_TIMEOUT_S = 8.0
T2_FEEDBACK_S = 1.2

# ------------------------------------------------ Task 3: STEADY BEAM
T3_ROUNDS = 2
T3_DURATION_S = 25.0
T3_ON_TARGET_PX = 30                  # within this distance = "on target"
T3_FLASHES = (7, 10)                  # total flashes per round
T3_GREEN = (3, 6)                     # how many of them are green
T3_FLASH_S = 0.4
T3_FLASH_GAP_S = 1.4                  # minimum gap between flashes
T3_ANSWER_MAX = 8                     # answer buttons 0..8
T3_ANSWER_TIMEOUT_S = 8.0

# ------------------------------------------------ baseline / readiness
FAMILIARISATION_SESSIONS = 3          # same as NASA's WinSCAT protocol (3 orientation sessions)
BASELINE_MIN_SESSIONS = 3
BASELINE_MAX_SESSIONS = 10
HIGH_CONFIDENCE_SESSIONS = 5
Z_FLAG = 2.0

# key, direction (+1 higher is worse / -1 lower is worse), spread floor, generic limit, component, label
METRICS = [
    ("t1_order_acc",     -1, 0.05, 0.80, "memory",    "port order accuracy"),
    ("t2_accuracy",      -1, 0.08, 0.70, "memory",    "satellite tracking accuracy"),
    ("t1_click_err_px",  +1, 2,    14,   "hand_eye",  "click error on ports (px)"),
    ("t1_click_time_ms", +1, 60,   1200, "hand_eye",  "time between port clicks (ms)"),
    ("t3_track_err_px",  +1, 3,    40,   "hand_eye",  "laser tracking error (px)"),
    ("t3_on_target_pct", -1, 4,    60,   "hand_eye",  "laser time on target (%)"),
    ("t3_count_err",     +1, 1,    2,    "attention", "green-flash counting error"),
    ("t2_select_time_ms", +1, 300, 4000, "attention", "time to pick tracked satellites (ms)"),
]
COMPONENTS = ["hand_eye", "memory", "attention"]

SHORT_SLEEP_H = 6.0
HIGH_FATIGUE = 5
