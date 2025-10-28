import os
import json

# --- Default strategy parameters ---
START_BANKROLL = 20.0
FLAT_BET_AMOUNT = 2.0  # Flat $2 bet per game
FILTER_FOLDER = "filter"


def incremental_ema_smooth(alpha=0.25):
    """
    Returns a function to incrementally smooth incoming points using an EMA.
    Causal and low-lag. alpha controls responsiveness (0 < alpha <= 1).
    """
    last = None

    def smooth_next(new_point):
        nonlocal last
        if last is None:
            last = new_point
        else:
            last = alpha * new_point + (1 - alpha) * last
        return last

    return smooth_next


def run_simulation(
    min_start=0.14,
    max_start=0.77,
    gain_threshold=0.03,
    halftime_fraction=1.0,
    fall_fraction=0.81,
    ema_alpha=0.25  # <-- configurable EMA smoothing factor
):
    bankroll = START_BANKROLL

    def get_game_pairs(folder):
        files = [f for f in os.listdir(folder) if f.endswith(".json")]
        games = {}
        for f in files:
            parts = f.rsplit("-", 1)
            game_key = parts[0]
            games.setdefault(game_key, []).append(f)
        return {k: v for k, v in games.items() if len(v) == 2}

    def simulate_position(data):
        prices = [e["price_cents"] / 100 if e["price_cents"] is not None else None for e in data]
        valid_prices = [p for p in prices if p is not None]
        if not valid_prices:
            return 0.0

        # --- incremental EMA smoothing ---
        smoother = incremental_ema_smooth(alpha=ema_alpha)
        smoothed_full = []
        for p in prices:
            if p is None:
                smoothed_full.append(None)
            else:
                smoothed_full.append(smoother(p))

        start_price = next((p for p in smoothed_full if p is not None), None)
        if start_price is None or not (min_start <= start_price <= max_start):
            return 0.0

        stake = FLAT_BET_AMOUNT
        max_gain = 0
        sell_price = None
        halftime_index = int(len(smoothed_full) * halftime_fraction)

        for idx, smooth_price in enumerate(smoothed_full):
            if smooth_price is None:
                continue
            real_price = prices[idx]
            if real_price is None:
                continue

            gain = smooth_price - start_price
            max_gain = max(max_gain, gain)

            # --- Sell conditions based on EMA-smoothed data ---
            if max_gain >= gain_threshold and gain < gain_threshold:
                sell_price = real_price
                break
            if max_gain > gain_threshold and gain <= max_gain * fall_fraction:
                sell_price = real_price
                break
            if idx == halftime_index and smooth_price < start_price + gain_threshold:
                sell_price = real_price
                break

        if sell_price is None:
            sell_price = next((p for p in reversed(prices) if p is not None), start_price)

        return stake * ((sell_price / start_price) - 1)

    # --- Process all weeks and games ---
    for week_name in sorted(os.listdir(FILTER_FOLDER)):
        week_path = os.path.join(FILTER_FOLDER, week_name)
        if not os.path.isdir(week_path):
            continue

        game_pairs = get_game_pairs(week_path)
        for game_key, files in game_pairs.items():
            game_profit = 0
            for f in files:
                file_path = os.path.join(week_path, f)
                with open(file_path, "r") as json_file:
                    data = json.load(json_file)
                game_profit += simulate_position(data)
            bankroll += game_profit

    return bankroll


if __name__ == "__main__":
    final_bankroll = run_simulation(
        ema_alpha=0.3  # smaller alpha = smoother, larger alpha = more reactive
    )
    print(f"Final bankroll: ${final_bankroll:.2f}")
