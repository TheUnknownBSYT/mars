"""
ORBIT OPS - all settings in one place.

Change numbers here, never inside the game code, so every session uses
exactly the same rules (this is what keeps the reaction-time data comparable
from day to day).
"""
from pathlib import Path

TASK_VERSION = "orbitops-py-1.0"

# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_CSV = DATA_DIR / "sessions.csv"
TRIALS_CSV = DATA_DIR / "trials.csv"
PROGRESS_JSON = DATA_DIR / "progress.json"

# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------
WIDTH, HEIGHT = 1280, 720
FPS_MENU = 60          # normal frame rate for menus
FPS_PRECISE = 1000     # rounds: poll the keyboard ~every 1 ms

# --------------------------------------------------------------------------
# General reaction-time rules (same as NASA's PVT-B where possible)
# --------------------------------------------------------------------------
FALSE_START_MS = 100   # responses faster than this are anticipations (guesses)

# --------------------------------------------------------------------------
# Round 1 - "Master Alarm"  (alertness, PVT-B style)
# --------------------------------------------------------------------------
R1_TRIALS = 30
R1_ISI_S = (1.0, 4.0)          # random wait before the alarm (PVT-B uses 1-4 s)
R1_TIMEOUT_S = 2.0             # no response after this = miss
R1_LAPSE_MS = 355              # PVT-B lapse threshold
R1_FEEDBACK_S = 0.6

# --------------------------------------------------------------------------
# Round 2 - "Debris Watch"  (go / no-go: decision speed + self-control)
# --------------------------------------------------------------------------
R2_TRIALS = 25
R2_GO_TRIALS = 18              # debris (press);  the other 7 are satellites (hold)
R2_ISI_S = (0.8, 1.6)
R2_WINDOW_S = 1.0              # time allowed to respond
R2_FEEDBACK_S = 0.5

# --------------------------------------------------------------------------
# Round 3 - "Mission Control Orders"  (task switching: adaptation)
# --------------------------------------------------------------------------
R3_TRIALS = 24
R3_BLOCK_LEN = (3, 5)          # rule changes every 3-5 trials
R3_ISI_S = (0.5, 0.9)
R3_WINDOW_S = 2.5
R3_NEW_ORDERS_S = 1.3          # "NEW ORDERS" banner before a switch trial
R3_FEEDBACK_S = 0.45
R3_CONGRUENT_SHARE = 1 / 3     # trials where both rules give the same key

# Response keys for Round 3 (left thruster / right thruster)
R3_LEFT_KEY_NAME = "F"
R3_RIGHT_KEY_NAME = "J"
# Mapping: SHAPE rule  triangle -> LEFT, circle -> RIGHT
#          COLOR rule  orange   -> LEFT, blue   -> RIGHT
R3_SHAPE_MAP = {"triangle": "left", "circle": "right"}
R3_COLOR_MAP = {"orange": "left", "blue": "right"}

# Practice trials per round (not scored, shown on first session or practice mode)
PRACTICE_TRIALS = {1: 4, 2: 5, 3: 6}

BREATHER_S = 5.0               # rest between rounds

# --------------------------------------------------------------------------
# Baseline + readiness rules
# --------------------------------------------------------------------------
FAMILIARISATION_SESSIONS = 3   # first sessions = learning the game, not used for baseline
BASELINE_MIN_SESSIONS = 3      # need at least this many to use a personal baseline
BASELINE_MAX_SESSIONS = 10     # rolling window (most recent valid sessions)
HIGH_CONFIDENCE_SESSIONS = 5

Z_SLOWER = 2.0                 # flag if more than 2 robust SDs worse than normal
Z_SWITCH_COST = 2.5

# Minimum spread so tiny baselines don't create false alarms
SPREAD_FLOORS = {
    "r1_median_ms": 15,
    "r1_lapses": 1.0,
    "decision_time_ms": 25,
    "r2_false_alarms": 1.0,
    "switch_cost_ms": 40,
    "r3_accuracy": 0.05,
}

# Generic reference thresholds (used ONLY until a personal baseline exists)
GENERIC = {
    "r1_median_ms": 380,
    "r1_lapses": 5,
    "r2_false_alarms": 3,
    "r2_accuracy": 0.80,
    "r3_accuracy": 0.75,
}

SHORT_SLEEP_H = 6.0
HIGH_FATIGUE = 5               # Samn-Perelli 1-7

# Data-quality checks -> RETEST
MAX_FALSE_STARTS = 5
MIN_VALID_R1 = 15
MAX_R3_TIMEOUTS = 8

# --------------------------------------------------------------------------
# Progression
# --------------------------------------------------------------------------
RANKS = [  # (sessions completed, title) - based on consistency, never speed
    (0, "Cadet"),
    (3, "Pilot Trainee"),
    (7, "Pilot"),
    (14, "Senior Pilot"),
    (30, "Commander"),
]
MODULE_EVERY = 5               # unlock a station module every N sessions
STATION_MODULES = [
    "Core Node", "Solar Array", "Habitat", "Greenhouse", "Science Lab",
    "Observation Cupola", "Robotic Arm", "Airlock", "Comms Tower", "Docking Hub",
]
