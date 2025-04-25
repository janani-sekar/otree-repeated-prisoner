import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- Helper functions ---
def quantile_geom(p, q):
    return int(np.ceil(np.log(1 - q) / np.log(1 - p)))

def sample_game_length(delta, cap_rounds=50):
    p = 1 - delta
    return min(np.random.geometric(p), cap_rounds)

# --- Simulation parameters ---
np.random.seed(0)
n_sims         = 100_000
delta_low      = 0.5
delta_high     = 0.95
cap_delta      = 0.95
cap_quantile   = 0.9
per_round_times = [90, 60, 30, 15]  # in seconds
wage_per_hour  = 8.0                # $8 / hr

# 1. Compute cap on rounds
cap_rounds = quantile_geom(1 - cap_delta, cap_quantile)

# 2. Sample deltas and game lengths
deltas  = np.random.uniform(delta_low, delta_high, size=n_sims)
lengths = np.array([sample_game_length(d) for d in deltas])

# 3. Compute overall game‐length stats (in rounds)
mean_rounds   = lengths.mean()
median_rounds = np.median(lengths)
min_rounds    = lengths.min()
max_rounds    = lengths.max()
first_quartile = np.percentile(lengths, 25)
third_quartile = np.percentile(lengths, 75)
five_quantile = np.percentile(lengths, 5)
ninetyfive_quantile = np.percentile(lengths, 95)
print(f"Mean game length:   {mean_rounds:.2f} rounds")
print(f"Median game length: {median_rounds:.0f} rounds")
print(f"Min game length:    {min_rounds} rounds")
print(f"Max game length:    {max_rounds} rounds\n")

# 4. Convert durations to minutes for each timing condition
durations_min = {t: (lengths * t) / 60.0 for t in per_round_times}

# 5. Compute stats, pay, and build table including min/max
rows = []
for t, d_min in durations_min.items():
    mean_dur   = d_min.mean()
    median_dur = np.median(d_min)
    min_dur    = d_min.min()
    max_dur    = d_min.max()
    mean_pay   = (mean_dur / 60.0) * wage_per_hour
    med_pay    = (median_dur / 60.0) * wage_per_hour

    rows.append({
        "Sec/Round":         t,
        "Min Rounds":        int(min_rounds),
        "Mean Rounds":       round(mean_rounds,   2),
        "Median Rounds":     int(median_rounds),
        "Max Rounds":        int(max_rounds),
        "Min Dur (min)":     round(min_dur,    2),
        "Mean Dur (min)":    round(mean_dur,   2),
        "Median Dur (min)":  round(median_dur, 2),
        "Max Dur (min)":     round(max_dur,    2),
        "Mean Pay ($)":      round(mean_pay,   2),
        "Median Pay ($)":    round(med_pay,    2),
        "5th Percentile":    round(five_quantile, 2),
        "95th Percentile":   round(ninetyfive_quantile, 2),
        "First Quartile":    round(first_quartile, 2),
        "Third Quartile":    round(third_quartile, 2),
    })

df_stats = pd.DataFrame(rows)
df_stats.to_csv("./payment_simulations.csv", index=False)
print(df_stats.to_string(index=False))

# 6. Visualize: overlayed histograms (x-axis in minutes)
plt.figure(figsize=(10, 6))
bins = 50
for t, d_min in durations_min.items():
    plt.hist(d_min, bins=bins, alpha=0.5, label=f'{t} s/round')

plt.title('Overlayed Game Duration Distributions')
plt.xlabel('Duration (minutes)')
plt.ylabel('Frequency')
plt.legend()
plt.tight_layout()
plt.show()
