"""One picture for the pitch: every variant, false alarms vs illnesses caught."""
import glob
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

frames = [pd.read_csv(f) for f in sorted(glob.glob("results/stage*.csv")) if "stage3" not in f]
d = pd.concat(frames, ignore_index=True).drop_duplicates("config")
final = pd.read_csv("results/final_test_on_new_crews.csv")

fig, ax = plt.subplots(figsize=(8, 5))
ax.scatter(d["false_alarm_days_per_month"], d["acute_recall"] * 100, s=14, color="#b8b8b8",
           label="variants tried (tuning crews)")
colors = {"STRICT": "#2e9d5b", "BALANCED": "#3b7dd8", "naive": "#d03b3b"}
for _, r in final.iterrows():
    key = next(k for k in colors if r["which"].startswith(k))
    ax.scatter(r["false_alarm_days_per_month"], r["acute_recall"] * 100, s=80, color=colors[key],
               zorder=3, label=f"{r['which'].split(' (')[0]} (new crews)")
ax.axvspan(0, 1, color="#2e9d5b", alpha=0.07)
ax.text(0.05, 8, "alarm budget\n1 per month", fontsize=9, color="#2e7d4b")
ax.set_xscale("symlog", linthresh=1)
ax.set_xlabel("false-alarm days per astronaut per month (log scale)")
ax.set_ylabel("illnesses caught (%)")
ax.set_ylim(0, 105)
ax.set_title("More alarms catch more, until nobody listens", loc="left")
ax.legend(fontsize=8, loc="lower right")
ax.grid(alpha=0.2)
fig.tight_layout()
fig.savefig("results/tradeoff.png", dpi=130)
print("saved results/tradeoff.png")
