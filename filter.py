import os
import json
import csv
from datetime import datetime, timedelta

# --- CONFIG ---
GAMES_FOLDER = "games"
OUTPUT_FOLDER = "filter"
SUMMARY_FILE = os.path.join(OUTPUT_FOLDER, "summary.csv")

FIRST_THURSDAY = datetime(2025, 9, 4)  # start of week 1
MINUTE_WINDOW = 10                       # number of minutes to check for price variability
VARIABILITY_THRESHOLD = 4               # minimum meaningful price changes within a window
MIN_PRICE_MOVE = 2                       # minimum price_cents change to count as meaningful
PRE_GAME_BUFFER = timedelta(minutes=10) # capture 10 minutes before kickoff
CONSECUTIVE_WINDOWS = 4                 # require consecutive windows meeting threshold

# --- Create week boundaries (Thursdays) ---
def generate_weeks(num_weeks=18):
    weeks = []
    for i in range(num_weeks):
        start = FIRST_THURSDAY + timedelta(weeks=i)
        end = start + timedelta(weeks=1)
        weeks.append((i + 1, start, end))
    return weeks

weeks = generate_weeks()

def get_week_number(dt):
    for week_num, start, end in weeks:
        if start <= dt < end:
            return week_num
    return None

# --- Kickoff detection with consecutive windows ---
def detect_kickoff(entries, minute_window=MINUTE_WINDOW, 
                    variability_threshold=VARIABILITY_THRESHOLD, 
                    min_price_move=MIN_PRICE_MOVE,
                    consecutive_windows=CONSECUTIVE_WINDOWS):
    """
    Detect kickoff by requiring multiple consecutive windows with meaningful price moves.
    """
    if len(entries) < minute_window:
        return None

    # Fill missing values with last valid price
    filled = []
    last_valid = None
    for e in entries:
        price = e["price_cents"]
        if price is None:
            if last_valid is not None:
                filled.append({"time": e["time"], "price_cents": last_valid})
        else:
            filled.append(e)
            last_valid = price

    if not filled:
        return None

    consecutive_count = 0
    for i in range(len(filled) - minute_window):
        window = filled[i:i + minute_window]
        prices = [e["price_cents"] for e in window]
        changes = sum(abs(prices[j] - prices[j - 1]) >= min_price_move for j in range(1, len(prices)))

        if changes >= variability_threshold:
            consecutive_count += 1
            if consecutive_count >= consecutive_windows:
                return datetime.fromisoformat(filled[i - consecutive_windows + 1]["time"])
        else:
            consecutive_count = 0

    # Fallback: first valid price
    return datetime.fromisoformat(filled[0]["time"])

# --- Helper to fill or clean nulls ---
def fill_null_prices(data):
    """
    Replaces None with previous valid value, and removes leading None entries.
    """
    cleaned = []
    last_valid = None
    for entry in data:
        price = entry["price_cents"]
        if price is None:
            if last_valid is not None:
                entry["price_cents"] = last_valid
                cleaned.append(entry)
        else:
            last_valid = price
            cleaned.append(entry)
    return cleaned

# --- Main processing ---
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
summary_rows = [("filename", "week", "kickoff_time", "entries_kept")]

for filename in os.listdir(GAMES_FOLDER):
    if not filename.endswith(".json"):
        continue

    filepath = os.path.join(GAMES_FOLDER, filename)
    with open(filepath, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Skipping {filename}: invalid JSON.")
            continue

    # Sort by time
    data.sort(key=lambda x: x["time"])

    kickoff = detect_kickoff(data)
    if not kickoff:
        print(f"⚠️ No kickoff detected for {filename}, skipping.")
        continue

    start_time = kickoff - PRE_GAME_BUFFER
    filtered = [e for e in data if datetime.fromisoformat(e["time"]) >= start_time]

    # Clean null prices
    filtered = fill_null_prices(filtered)
    if not filtered:
        print(f"⚠️ All entries null after filtering for {filename}, skipping.")
        continue

    # Determine week (based on kickoff)
    week_num = get_week_number(kickoff)
    if not week_num:
        print(f"⚠️ Could not determine week for {filename}, skipping.")
        continue

    week_folder = os.path.join(OUTPUT_FOLDER, f"week{week_num}")
    os.makedirs(week_folder, exist_ok=True)

    out_path = os.path.join(week_folder, filename)
    with open(out_path, "w") as f:
        json.dump(filtered, f, indent=2)

    summary_rows.append((filename, week_num, kickoff.isoformat(), len(filtered)))
    print(f"✅ Filtered {filename} → {out_path} ({len(filtered)} entries)")

# --- Write summary CSV ---
with open(SUMMARY_FILE, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerows(summary_rows)

print(f"\nSummary written to {SUMMARY_FILE}")
