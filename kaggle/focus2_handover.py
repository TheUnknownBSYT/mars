"""
Mission Pulse - Focus 2: the HANDOVER chart (building on NASA's EIMO)
====================================================================
Question it answers: "On which mission day is each astronaut's onboard health
model trustworthy enough to run without Earth, and is that BEFORE Earth stops
being able to help in real time?"

Two curves against mission day:
  1. READINESS (rises): from baseline 2. Each signal's confidence grows with
     good days (up to 40) and becomes 100% when its space normal locks
     (stable for 2 weeks). An astronaut is handover-ready when ALL signals lock.
  2. EARTH DELAY (rises): one-way signal delay to Earth on a Mars transfer,
     computed from orbital mechanics (simplified: circular, flat planet orbits
     and a minimum-energy transfer of ~259 days). Also checks for solar
     conjunction (spacecraft behind the Sun as seen from Earth = blackout).

Handover deadline = first day the one-way delay passes MAX_ONE_WAY_MIN
(default 5 min, i.e. a 10-minute round trip: past this, a back-and-forth
conversation with a flight surgeon during an emergency isn't practical),
or the start of a blackout, whichever comes first.
Margin = deadline - ready day. Positive = safe. Negative = not ready in time
-> those signals stay GREY and the crew is told so.

The 5-minute rule is OUR assumption, not a NASA number; it's one setting below.
NASA's own detailed delay modelling (ASCEND paper) gives 0-22 min over a full
Mars mission; our simple orbit model is for the transit leg only.

Kaggle: run the baseline 1 and baseline 2 cells first, then this one.
No inputs. Outputs: handover_chart.png, handover_timeline.csv, handover_summary.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from baseline2_space_normal import run_crew as run_space_crew, demo_crew, MIN_DAYS_READY
except ImportError:
    if "demo_crew" not in globals():
        raise ImportError("Run the baseline 1 and baseline 2 cells first.")
    run_space_crew = run_crew  # noqa: F821  (baseline 2's function from the earlier cell)

# ---- settings ----------------------------------------------------------------
MAX_ONE_WAY_MIN = 5.0      # handover deadline: one-way delay beyond this (minutes)
CONJUNCTION_DEG = 3.0      # Sun-Earth-spacecraft angle below this = blackout
TRANSIT_DAYS = None        # None = full minimum-energy transfer (~259 days)

AU_KM = 149_597_870.7
C_KM_S = 299_792.458
R_EARTH, R_MARS = 1.0, 1.524   # AU
YEAR_D = 365.25


def mars_transfer_delay(days: np.ndarray) -> pd.DataFrame:
    """One-way light delay (min) and Sun-Earth-spacecraft angle (deg) per mission day."""
    a = (R_EARTH + R_MARS) / 2
    e = (R_MARS - R_EARTH) / (R_MARS + R_EARTH)
    period = a ** 1.5 * YEAR_D
    n = 2 * np.pi / period
    rows = []
    for t in days:
        M = n * t
        E = M
        for _ in range(50):                              # Kepler's equation
            E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        nu = 2 * np.arctan(np.sqrt((1 + e) / (1 - e)) * np.tan(E / 2))
        r = a * (1 - e * np.cos(E))
        sc = np.array([r * np.cos(nu), r * np.sin(nu)])
        th = 2 * np.pi * t / YEAR_D
        earth = np.array([np.cos(th), np.sin(th)])
        d = np.linalg.norm(sc - earth)
        to_sun, to_sc = -earth, sc - earth
        if d < 1e-9:                                     # launch day: craft is at Earth
            ang = 180.0
        else:
            ang = np.degrees(np.arccos(np.clip(to_sun @ to_sc / (np.linalg.norm(to_sun) * d), -1, 1)))
        rows.append(dict(day=int(t), distance_au=round(d, 4),
                         one_way_delay_min=round(d * AU_KM / C_KM_S / 60, 2),
                         sun_earth_craft_deg=round(ang, 1)))
    return pd.DataFrame(rows)


def readiness_by_day(space_daily: pd.DataFrame, days: np.ndarray) -> pd.DataFrame:
    """Per astronaut per day: readiness % (mean signal confidence) and signals locked."""
    d = space_daily.copy()
    d["confidence"] = np.where(d["locked"], 1.0, np.clip(d["good_days"] / MIN_DAYS_READY, 0, 1) * 0.9)
    g = d.groupby(["astronaut", "day"]).agg(readiness=("confidence", "mean"),
                                            signals_locked=("locked", "sum"),
                                            signals=("locked", "size")).reset_index()
    # carry the last value forward if the data is shorter than the transit
    out = []
    for a, ga in g.groupby("astronaut"):
        ga = ga.set_index("day").reindex(days).ffill()
        ga["astronaut"] = a
        out.append(ga.reset_index())
    return pd.concat(out, ignore_index=True)


def main():
    pre, mis = demo_crew()
    space_daily, space_summary = run_space_crew(mis)

    transit = TRANSIT_DAYS or int(round(((R_EARTH + R_MARS) / 2) ** 1.5 * YEAR_D / 2))
    days = np.arange(transit + 1)
    earth = mars_transfer_delay(days)
    ready = readiness_by_day(space_daily, days)

    over = earth.loc[earth.one_way_delay_min > MAX_ONE_WAY_MIN, "day"]
    delay_deadline = int(over.min()) if len(over) else None
    blackout = earth.loc[earth.sun_earth_craft_deg < CONJUNCTION_DEG, "day"]
    blackout_start = int(blackout.min()) if len(blackout) else None
    deadline = min(x for x in (delay_deadline, blackout_start) if x is not None) \
        if (delay_deadline or blackout_start) else None

    rows = []
    for a, g in space_summary.groupby("astronaut"):
        ready_day = int(g["lock_day"].max()) if g["lock_day"].notna().all() else None
        margin = (deadline - ready_day) if (deadline is not None and ready_day is not None) else None
        rows.append(dict(astronaut=a, handover_ready_day=ready_day,
                         slowest_signal=g.loc[g["lock_day"].idxmax(), "signal"],
                         deadline_day=deadline, margin_days=margin,
                         status=("READY in time" if margin is not None and margin >= 0
                                 else "NOT READY by deadline (signals stay grey)")))
    summary = pd.DataFrame(rows)

    timeline = ready.pivot(index="day", columns="astronaut", values="readiness").add_prefix("readiness_")
    timeline["crew_readiness_min"] = timeline.min(axis=1)
    timeline = timeline.reset_index().merge(earth, on="day")
    timeline.to_csv("handover_timeline.csv", index=False)
    summary.to_csv("handover_summary.csv", index=False)

    # ---------------- the chart ----------------
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    for a, g in ready.groupby("astronaut"):
        ax1.plot(g["day"], g["readiness"] * 100, lw=1.2, alpha=0.55, label=f"{a} readiness")
    ax1.plot(timeline["day"], timeline["crew_readiness_min"] * 100, color="#2e9d5b", lw=2.6,
             label="crew readiness (slowest astronaut)")
    ax1.set_ylabel("onboard model readiness (%)")
    ax1.set_ylim(0, 105)
    ax1.set_xlabel("mission day (Earth to Mars transit)")

    ax2 = ax1.twinx()
    ax2.plot(earth["day"], earth["one_way_delay_min"], color="#d03b3b", lw=2.2, label="one-way delay to Earth")
    ax2.axhline(MAX_ONE_WAY_MIN, color="#d03b3b", ls=":", lw=1)
    ax2.set_ylabel("one-way signal delay to Earth (minutes)", color="#d03b3b")
    ax2.set_ylim(0, max(earth["one_way_delay_min"].max() * 1.1, MAX_ONE_WAY_MIN * 1.5))

    crew_ready = summary["handover_ready_day"].max()
    ax1.axvspan(0, 14, color="#9a9a9a", alpha=0.12)
    ax1.text(1, 97, "settling\nin", fontsize=8, color="#666", va="top")
    if crew_ready is not None:
        ax1.axvline(crew_ready, color="#2e9d5b", ls="--", lw=1.5)
        ax1.text(crew_ready + 2, 20, f"crew handover-ready\nday {crew_ready}", color="#2e7d4b", fontsize=9)
    if deadline is not None:
        ax1.axvline(deadline, color="#d03b3b", ls="--", lw=1.5)
        ax1.text(deadline + 2, 30, f"deadline: delay > {MAX_ONE_WAY_MIN:g} min\nday {deadline}",
                 color="#a02020", fontsize=9)
        if crew_ready is not None and crew_ready <= deadline:
            ax1.axvspan(crew_ready, deadline, color="#2e9d5b", alpha=0.10)
            ax1.text((crew_ready + deadline) / 2, 55, f"{deadline - crew_ready}-day\nsafety margin",
                     ha="center", fontsize=10, color="#2e7d4b", weight="bold")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="center right")
    ax1.set_title("The onboard health model is ready before Earth stops being able to help", loc="left")
    ax1.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig("handover_chart.png", dpi=140)

    pd.set_option("display.width", 200)
    print(summary.to_string(index=False))
    print(f"\nDelay passes {MAX_ONE_WAY_MIN:g} min one way on day {delay_deadline}; "
          f"max delay on transit {earth.one_way_delay_min.max()} min (day {int(earth.one_way_delay_min.idxmax())}); "
          f"blackout during transit: {'day ' + str(blackout_start) if blackout_start is not None else 'none'} "
          f"(min Sun-Earth-craft angle {earth.sun_earth_craft_deg.min()} deg)")
    print("\nDelay on key days:")
    print(earth[earth.day.isin([0, 15, 30, 45, 60, 90, 120, 180, transit])].to_string(index=False))
    return summary, timeline


if __name__ == "__main__":
    main()
