import os
import csv
import time
import numpy as np
from itertools import product
from multiprocessing import Pool, cpu_count
from one_buy import run_simulation  # Make sure this uses EMA internally

# --- Parameter ranges: (start, stop, step) ---
MIN_START_RANGE = (0.14, 0.15, 0.01)
MAX_START_RANGE = (0.71, 0.73, 0.01)
GAIN_THRESHOLD_RANGE = (0.02, 0.03, 0.01)
FALL_FRACTION_RANGE = (0.79, 0.81, 0.01)
ALPHA_RANGE = (0.2, 0.4, 0.01)  # EMA smoothing factor
HALFTIME_FRACTION = 1.0  # Fixed

# --- Generate all combinations ---
min_starts = np.arange(*MIN_START_RANGE)
max_starts = np.arange(*MAX_START_RANGE)
gain_thresholds = np.arange(*GAIN_THRESHOLD_RANGE)
fall_fractions = np.arange(*FALL_FRACTION_RANGE)
alphas = np.arange(*ALPHA_RANGE)

param_combos = [
    (min_start, max_start, gain_th, fall_frac, alpha)
    for min_start, max_start, gain_th, fall_frac, alpha in product(
        min_starts, max_starts, gain_thresholds, fall_fractions, alphas
    )
    if max_start > min_start  # ensure valid range
]

total_combos = len(param_combos)
print(f"🧮 Total parameter combinations: {total_combos}")

# --- Worker for a batch ---
def run_batch(batch):
    results = []
    for min_start, max_start, gain_th, fall_frac, alpha in batch:
        bankroll = run_simulation(
            min_start=min_start,
            max_start=max_start,
            gain_threshold=gain_th,
            fall_fraction=fall_frac,
            ema_alpha=alpha,         # Pass EMA alpha to simulation
            halftime_fraction=HALFTIME_FRACTION
        )
        results.append((
            round(min_start, 3),
            round(max_start, 3),
            round(gain_th, 3),
            round(fall_frac, 3),
            round(alpha, 3),
            round(bankroll, 2)
        ))
    return results

# --- Split work into chunks ---
num_cores = max(1, cpu_count() - 1)
chunk_size = int(np.ceil(total_combos / num_cores))
chunks = [param_combos[i:i + chunk_size] for i in range(0, total_combos, chunk_size)]
print(f"⚙️ Using {num_cores} CPU cores (~{chunk_size} combos per core)")

# --- Run parameter sweep ---
start_time = time.time()
all_results = []
completed = 0
os.makedirs("sweeps", exist_ok=True)

with Pool(num_cores) as pool:
    for batch_result in pool.imap_unordered(run_batch, chunks):
        all_results.extend(batch_result)
        completed += len(batch_result)
        if completed % 50 == 0 or completed == total_combos:
            elapsed = time.time() - start_time
            best_so_far = max(all_results, key=lambda r: r[-1])
            progress = min(100, completed / total_combos * 100)
            print(f"Progress: {progress:.2f}% | Completed: {completed}/{total_combos} | "
                  f"Best bankroll so far: ${best_so_far[-1]:.2f} | Elapsed: {elapsed/60:.1f} min")

# --- Save CSV ---
csv_path = os.path.join("sweeps", "sweep_ema_results.csv")
with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["MIN_START","MAX_START","GAIN_THRESHOLD","FALL_FRACTION","ALPHA","FINAL_BANKROLL"])
    writer.writerows(all_results)

# --- Best result ---
best = max(all_results, key=lambda r: r[-1])
print("\n🏆 Best parameters found:")
print(f"MIN_START: {best[0]}")
print(f"MAX_START: {best[1]}")
print(f"GAIN_THRESHOLD: {best[2]}")
print(f"FALL_FRACTION: {best[3]}")
print(f"EMA ALPHA: {best[4]}")
print(f"Best bankroll: ${best[5]:.2f}")
print(f"Results saved to {csv_path}")
