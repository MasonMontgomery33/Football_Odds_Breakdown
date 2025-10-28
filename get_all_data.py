import requests
import json
import os
from datetime import datetime, timedelta

def create_games_folder():
    """Create games folder if it doesn't exist"""
    if not os.path.exists('games'):
        os.makedirs('games')

def get_nfl_markets_after_date(cutoff_date):
    """Get NFL markets from September 4th, 2025 onwards"""
    all_markets = []
    cursor = None
    base_url = "https://api.elections.kalshi.com/trade-api/v2/markets"
    
    while True:
        url = f"{base_url}?series_ticker=KXNFLGAME&limit=1000"
        if cursor:
            url += f"&cursor={cursor}"
        
        response = requests.get(url)
        data = response.json()
        
        # Filter markets by date (check if ticker contains date >= Sept 4, 2025)
        for market in data['markets']:
            # Extract date from ticker (format: KXNFLGAME-25SEP04... or KXNFLGAME-25OCT05...)
            ticker = market['ticker']
            if '-25' in ticker:  # 2025 games
                # Extract month and day
                date_part = ticker.split('-')[1]  # Gets "25SEP04NEBUF" part
                if len(date_part) >= 7:
                    month_day = date_part[2:7]  # Gets "SEP04" part
                    
                    # Convert to comparable format
                    if (month_day >= "SEP04" or 
                        month_day.startswith("OCT") or 
                        month_day.startswith("NOV") or 
                        month_day.startswith("DEC")):
                        all_markets.append(market)
        
        cursor = data.get('cursor')
        if not cursor:
            break
        
        print(f"Processed {len(data['markets'])} markets, filtered total: {len(all_markets)}")
    
    return all_markets

def get_market_candlesticks(series_ticker, market_ticker, market_data):
    """Get candlestick data for 8 hours before market close time"""
    
    # Get market close time
    if 'close_time' not in market_data or not market_data['close_time']:
        print(f"No close_time found for {market_ticker}")
        return {}
    
    # Parse close time (ISO format with Z)
    close_time_str = market_data['close_time']
    close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
    
    # Get 8 hours before close time
    start_time = close_time - timedelta(hours=8)
    
    start_ts = int(start_time.timestamp())
    end_ts = int(close_time.timestamp())
    
    print(f"Fetching data from {start_time} to {close_time}")
    
    url = f"https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}/markets/{market_ticker}/candlesticks"
    
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": 1  # 1 minute intervals
    }
    
    response = requests.get(url, params=params)
    return response.json()

def extract_minute_prices(candlestick_data):
    """Extract just the minute-by-minute prices"""
    minute_prices = []
    
    if 'candlesticks' in candlestick_data:
        for candle in candlestick_data['candlesticks']:
            time = datetime.fromtimestamp(candle['end_period_ts'])
            close_price = candle['price']['close']
            minute_prices.append({
                'time': time.isoformat(),
                'price_cents': close_price
            })
    
    return minute_prices

def save_minute_prices(market_ticker, minute_prices):
    """Save just the minute-by-minute prices to a file"""
    filename = f"games/{market_ticker}.json"
    
    with open(filename, 'w') as f:
        json.dump(minute_prices, f, indent=2)
    
    print(f"Saved {len(minute_prices)} price points to: {filename}")

def main():
    """Main function to process NFL games from Sept 4, 2025 onwards"""
    create_games_folder()
    
    cutoff_date = datetime(2025, 9, 4)
    print("Fetching NFL markets from September 4, 2025 onwards...")
    
    nfl_markets = get_nfl_markets_after_date(cutoff_date)
    print(f"Found {len(nfl_markets)} NFL markets from Sept 4, 2025+")
    
    for i, market in enumerate(nfl_markets):
        print(f"\nProcessing {i+1}/{len(nfl_markets)}: {market['ticker']}")
        print(f"Market close time: {market.get('close_time')}")
        
        # Get candlestick data for 8 hours before close
        candlestick_data = get_market_candlesticks("KXNFLGAME", market['ticker'], market)
        
        # Extract just minute prices
        minute_prices = extract_minute_prices(candlestick_data)
        
        if minute_prices:
            # Save to file
            save_minute_prices(market['ticker'], minute_prices)
        else:
            print(f"No price data found for {market['ticker']}")

if __name__ == "__main__":
    main()