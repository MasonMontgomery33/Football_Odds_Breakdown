import os
import json
import time
from collections import deque
from typing import Optional
from rich.console import Console
from rich.table import Table

# ---------- CONFIG ----------
ACTIVE_FOLDER = "active_games"     # folder containing ticker.jsonl files
BET_AMOUNT = 10.0                  # flat $10 bet per game
MIN_START = 0.14
MAX_START = 0.77
GAIN_THRESHOLD = 0.03
FALL_FRACTION = 0.81
SIGMA_REF = 3.32                   # original reference sigma (per minute)
SAMPLES_PER_MINUTE = 60.0          # we sample every second, so 60 samples/min
DISPLAY_INTERVAL = 10              # seconds between dashboard refresh (also immediate on sell)
HISTORY_LENGTH = 300               # keep last N raw prices if you want history (not required for EWMA)

# ---------- STATE ----------
console = Console()
smoothed = {}         # ticker -> current EWMA smoothed price (float)
price_history = {}    # ticker -> deque of raw prices (optional, for debugging)
active_bets = {}      # ticker -> {"bet": float, "start_price": float, "max_gain": float}
sold_games = {}       # ticker -> realized profit (float)
bankroll = 0.0        # starts at 0, only increases on sells

# ---------- HELPERS ----------
def load_last_price_from_jsonl(path: str) -> Optional[float]:
    """Return last valid 'price' (0-1) from a JSONL file, or None."""
    if not os.path.exists(path):
        return None
    last_price = None
    try:
        with open(path, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    p = obj.get("price")
                    if p is not None:
                        last_price = p / 100.0  # convert cents -> 0..1
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None
    return last_price

def ewma_update(prev: Optional[float], value: float, alpha: float) -> float:
    """One-step EWMA update (causal). If prev is None, return value."""
    if prev is None:
        return float(value)
    return alpha * float(value) + (1.0 - alpha) * float(prev)

def compute_alpha_from_sigma_minutes(sigma_minutes: float) -> float:
    """
    Translate Gaussian sigma (in minutes) to an EWMA alpha for per-second updates.
    Heuristic: sigma_points = sigma_minutes * samples_per_minute
    Choose alpha = 1 / (sigma_points) (small alpha -> smoother)
    Clip alpha to (0.001, 0.5) to be safe.
    """
    sigma_points = sigma_minutes * SAMPLES_PER_MINUTE
    alpha = 1.0 / max(1.0, sigma_points)
    # keep alpha in a sensible range
    alpha = max(0.001, min(alpha, 0.5))
    return alpha

ALPHA = compute_alpha_from_sigma_minutes(SIGMA_REF)  # small number, very smooth
# ---------- END HELPERS ----------

def place_initial_bets():
    """
    Read latest prices once and place bets immediately on tickers whose
    smoothed current price is within MIN_START..MAX_START.
    This runs only once at startup.
    """
    # initialize smoothed values for all tickers so EWMA uses initial value
    for fn in os.listdir(ACTIVE_FOLDER):
        if not fn.endswith(".jsonl"):
            continue
        ticker = fn[:-6]  # remove .jsonl
        path = os.path.join(ACTIVE_FOLDER, fn)
        last_price = load_last_price_from_jsonl(path)
        if last_price is None:
            continue
        # initialize smoothed and history
        smoothed[ticker] = last_price
        price_history.setdefault(ticker, deque(maxlen=HISTORY_LENGTH)).append(last_price)

    # place bets where smoothed price falls in range
    for ticker, s_price in list(smoothed.items()):
        if MIN_START <= s_price <= MAX_START:
            active_bets[ticker] = {"bet": BET_AMOUNT, "start_price": s_price, "max_gain": 0.0}
            console.print(f"💵 Placed ${BET_AMOUNT:.2f} bet on {ticker} at start price {s_price:.3f}")

def update_from_live_files() -> list:
    """
    Read the latest price for each ticker, update EWMA smoothed[ticker].
    Returns a list of tickers that were updated (have a new or existing smoothed value).
    """
    updated_tickers = []
    for fn in os.listdir(ACTIVE_FOLDER):
        if not fn.endswith(".jsonl"):
            continue
        ticker = fn[:-6]
        path = os.path.join(ACTIVE_FOLDER, fn)
        last_price = load_last_price_from_jsonl(path)
        if last_price is None:
            continue

        # initialize structures if missing
        if ticker not in smoothed:
            smoothed[ticker] = last_price
        else:
            smoothed[ticker] = ewma_update(smoothed[ticker], last_price, ALPHA)

        price_history.setdefault(ticker, deque(maxlen=HISTORY_LENGTH)).append(last_price)
        updated_tickers.append(ticker)
    return updated_tickers

def evaluate_sells_for_ticker(ticker: str) -> bool:
    """
    Update max_gain for active bet and evaluate sell conditions.
    If sell occurs, update bankroll and return True. Otherwise False.
    """
    global bankroll
    if ticker not in active_bets:
        return False
    if ticker not in smoothed:
        return False

    current = smoothed[ticker]
    bet = active_bets[ticker]
    start = bet["start_price"]

    gain = current - start
    if gain > bet["max_gain"]:
        bet["max_gain"] = gain

    # sell conditions (based on relative gains)
    sell = False
    if bet["max_gain"] >= GAIN_THRESHOLD and gain < GAIN_THRESHOLD:
        sell = True
    elif bet["max_gain"] > GAIN_THRESHOLD and gain <= bet["max_gain"] * FALL_FRACTION:
        sell = True

    if sell:
        # realized profit for binary-style price: bet * (p - start)
        profit = bet["bet"] * (current - start)
        bankroll += profit
        sold_games[ticker] = profit
        del active_bets[ticker]
        console.print(f"💰 SOLD {ticker} at {current:.3f} -> Profit: ${profit:.2f}", style="bold green")
        return True
    return False

def build_and_print_dashboard():
    """Show a clean dashboard; max_gain shown as decimal, P/L as dollars."""
    table = Table(title="Active Game Dashboard (smoothed prices)")
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("Current", justify="right")
    table.add_column("Max Gain", justify="right")
    table.add_column("Position", justify="right")
    table.add_column("Unrealized P/L", justify="right")
    table.add_column("Realized P/L", justify="right")

    # iterate sorted for stable display
    tickers = sorted(smoothed.keys())
    for ticker in tickers:
        cur = smoothed.get(ticker)
        cur_str = f"{cur:.3f}" if cur is not None else "-"
        if ticker in active_bets:
            bet = active_bets[ticker]
            max_gain = bet.get("max_gain", 0.0)
            unrealized = bet["bet"] * (cur - bet["start_price"])
            pos = f"${bet['bet']:.2f}"
            unreal_str = f"${unrealized:.2f}"
            maxgain_str = f"{max_gain:.3f}"
        else:
            pos = "-"
            unreal_str = "-"
            maxgain_str = "-" if ticker not in sold_games else "-"
        realized = f"${sold_games.get(ticker, 0.0):.2f}" if ticker in sold_games else "-"

        table.add_row(ticker, cur_str, maxgain_str, pos, unreal_str, realized)

    console.clear()
    console.print(table)
    console.print(f"💰 Total bankroll (realized only): ${bankroll:.2f}", style="bold magenta")

# ---------- MAIN ----------
def main_loop():
    # 1) place initial bets (once) using the latest available smoothed price
    place_initial_bets()

    last_display = 0.0
    while True:
        updated = update_from_live_files()  # refresh smoothed values using EWMA

        # Evaluate sells for any tickers that have active bets (every second)
        sell_happened = False
        for ticker in list(active_bets.keys()):
            if evaluate_sells_for_ticker(ticker):
                sell_happened = True

        # dashboard refresh: immediate on sell or at DISPLAY_INTERVAL
        now = time.time()
        if sell_happened or (now - last_display) >= DISPLAY_INTERVAL:
            build_and_print_dashboard()
            last_display = now

        time.sleep(1.0)

if __name__ == "__main__":
    if not os.path.isdir(ACTIVE_FOLDER):
        console.print(f"Active folder not found: {ACTIVE_FOLDER}", style="bold red")
    else:
        console.print(f"Alpha (EWMA) = {ALPHA:.6f}  |  SIGMA_REF={SIGMA_REF}min -> EWMA alpha computed", style="dim")
        try:
            main_loop()
        except KeyboardInterrupt:
            console.print("Exiting (keyboard interrupt).", style="bold yellow")