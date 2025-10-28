import websockets
import shutil
import asyncio
import json
import os
import time
import base64
import requests
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# --- Configuration ---
ACCESS_KEY = "ACCESS_KEY"
PRIVATE_KEY_PATH = "private_key.pem"
WS_PROD_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
API_BASE_URL = "https://api.elections.kalshi.com"
SERIES_TICKER = "KXNFLGAME"
ACTIVE_GAMES_FOLDER = "active_games"

# --- Helper Functions ---
def load_private_key(key_path):
    with open(key_path, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

def create_signature(private_key, timestamp, method, path):
    """Generate signature for WebSocket request"""
    message = timestamp + method + path
    sig = private_key.sign(
        message.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(sig).decode("utf-8")

def ensure_active_games_folder():
    if not os.path.exists(ACTIVE_GAMES_FOLDER):
        os.makedirs(ACTIVE_GAMES_FOLDER)

def parse_ticker_date(ticker: str):
    """
    Extract and parse the date from a ticker like 'KXNFLGAME-25OCT19ATLSF-SF'
    Returns a datetime.date object, or None if parsing fails.
    """
    try:
        # Split like ['KXNFLGAME', '25OCT19ATLSF-SF']
        parts = ticker.split('-')
        if len(parts) < 2:
            return None
        date_str = parts[1][:7]  # '25OCT19'
        date_obj = datetime.strptime(date_str, "%y%b%d").date()
        return date_obj
    except Exception:
        # Handle tickers with slightly different formats just in case
        try:
            date_str = parts[1][:7].upper()
            date_obj = datetime.strptime(date_str, "%y%b%d").date()
            return date_obj
        except Exception:
            return None

# --- Get Games Starting Today ---
def get_todays_nfl_games():
    url = f"{API_BASE_URL}/trade-api/v2/markets"
    params = {"series_ticker": SERIES_TICKER, "status": "open", "limit": 200}
    all_markets = []

    while True:
        response = requests.get(url, params=params)
        data = response.json()
        all_markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if cursor:
            params["cursor"] = cursor
        else:
            break

    today = datetime.utcnow().date()
    todays_games = []

    for market in all_markets:
        ticker = market.get("ticker", "")
        game_date = parse_ticker_date(ticker)
        if game_date == today:
            todays_games.append(market)

    # Sort by close_time (earliest first)
    todays_games.sort(key=lambda x: x.get("close_time"))
    return todays_games

# --- Main Monitoring Function ---
async def monitor_active_nfl_games():
    ensure_active_games_folder()
    private_key = load_private_key(PRIVATE_KEY_PATH)

    # Fetch today's NFL games
    games = get_todays_nfl_games()
    if not games:
        print("❌ No NFL games starting today.")
        return

    tickers = [m["ticker"] for m in games]
    print(f"✅ Monitoring {len(tickers)} NFL games starting today.")
    print("\n".join(f" - {t}" for t in tickers))

    last_data = {ticker: None for ticker in tickers}
    last_second = int(time.time())

    while True:
        try:
            path = "/trade-api/ws/v2"
            timestamp = str(int(time.time() * 1000))
            signature = create_signature(private_key, timestamp, "GET", path)

            async with websockets.connect(
                WS_PROD_URL,
                additional_headers=[
                    ("KALSHI-ACCESS-KEY", ACCESS_KEY),
                    ("KALSHI-ACCESS-SIGNATURE", signature),
                    ("KALSHI-ACCESS-TIMESTAMP", timestamp)
                ]
            ) as ws:
                subscribe_msg = {
                    "id": 1,
                    "cmd": "subscribe",
                    "params": {"channels": ["ticker"], "market_tickers": tickers}
                }
                await ws.send(json.dumps(subscribe_msg))
                print("✅ Connected! Streaming updates...")

                async for message in ws:
                    now_second = int(time.time())
                    data = json.loads(message)

                    if data.get("type") == "ticker":
                        msg_data = data.get("msg", {})
                        ticker = msg_data.get("market_ticker")
                        if ticker in tickers:
                            last_data[ticker] = msg_data

                    # record one datapoint per second per ticker
                    if now_second > last_second:
                        for ticker in tickers:
                            if last_data[ticker] is not None:
                                filename = f"{ACTIVE_GAMES_FOLDER}/{ticker}.jsonl"
                                last_data[ticker]['recorded_at'] = datetime.now().isoformat()
                                with open(filename, "a") as f:
                                    f.write(json.dumps(last_data[ticker]) + "\n")
                        last_second = now_second

        except websockets.exceptions.InvalidStatusCode as e:
            print(f"❌ Connection failed with status {e.status_code}. Retrying in 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"⚠️ Connection error: {e}. Retrying in 10s...")
            await asyncio.sleep(10)

# --- Run the Monitor ---
if __name__ == "__main__":
    asyncio.run(monitor_active_nfl_games())
