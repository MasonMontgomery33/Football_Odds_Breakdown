import os
import json
from datetime import datetime
import matplotlib.pyplot as plt

# --- configuration ---
FILTER_FOLDER = "filter"
GRAPH_FOLDER = "graphs"

# --- EMA parameters ---
EMA_ALPHA = 0.3  # smoothing factor: 0 < alpha <= 1, higher = more responsive

# ensure base graph directory exists
os.makedirs(GRAPH_FOLDER, exist_ok=True)

# use seaborn-like style for cleaner aesthetics
plt.style.use('seaborn-v0_8')

def remove_outliers(times, values):
    """Remove isolated spikes: if both neighbors are on the same side of a point."""
    if len(values) < 3:
        return times, values
    cleaned_times = [times[0]]
    cleaned_values = [values[0]]
    for i in range(1, len(values) - 1):
        prev_val, curr_val, next_val = values[i - 1], values[i], values[i + 1]
        if (prev_val > curr_val and next_val > curr_val) or (prev_val < curr_val and next_val < curr_val):
            continue  # skip spike
        cleaned_times.append(times[i])
        cleaned_values.append(curr_val)
    cleaned_times.append(times[-1])
    cleaned_values.append(values[-1])
    return cleaned_times, cleaned_values

def incremental_ema_smoother(alpha=EMA_ALPHA):
    """Returns a function to incrementally smooth points using EMA."""
    ema = None
    def smooth_next(point):
        nonlocal ema
        if ema is None:
            ema = point
        else:
            ema = alpha * point + (1 - alpha) * ema
        return ema
    return smooth_next

# --- loop through each week ---
for week_name in os.listdir(FILTER_FOLDER):
    week_path = os.path.join(FILTER_FOLDER, week_name)
    if not os.path.isdir(week_path):
        continue

    week_graph_folder = os.path.join(GRAPH_FOLDER, week_name)
    os.makedirs(week_graph_folder, exist_ok=True)

    # --- process each game JSON ---
    for filename in os.listdir(week_path):
        if not filename.endswith(".json"):
            continue

        file_path = os.path.join(week_path, filename)
        graph_path = os.path.join(week_graph_folder, filename.replace(".json", ".png"))

        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping {filename}: invalid JSON.")
                continue

        if not data:
            print(f"Skipping empty file: {filename}")
            continue

        # parse times and prices
        try:
            times = [datetime.fromisoformat(e["time"]) for e in data if e["price_cents"] is not None]
            prices = [e["price_cents"] / 100 for e in data if e["price_cents"] is not None]
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
            continue

        if len(times) < 3:
            print(f"Not enough data points in {filename}")
            continue

        # remove outliers
        cleaned_times, cleaned_prices = remove_outliers(times, prices)

        # incremental EMA smoothing
        smoother = incremental_ema_smoother(alpha=EMA_ALPHA)
        smoothed_prices = [smoother(p) for p in cleaned_prices]

        # detect kickoff time (first timestamp)
        kickoff_time = min(times)

        # --- plot ---
        plt.figure(figsize=(10, 6))
        plt.plot(times, prices, color="lightgray", alpha=0.5, label="Raw Price")
        plt.plot(cleaned_times, smoothed_prices, color="blue", linewidth=2, label="Smoothed Price (EMA)")
        plt.axvline(kickoff_time, color="red", linestyle="--", linewidth=1.5, label="Kickoff")
        plt.xlabel("Time")
        plt.ylabel("Win Probability")
        plt.title(f"Odds Movement - {filename}")
        plt.ylim(0, 1)
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        plt.savefig(graph_path)
        plt.close()

        print(f"Graph saved: {graph_path}")

print(f"\nAll graphs generated successfully with incremental EMA smoothing (alpha={EMA_ALPHA}).")
