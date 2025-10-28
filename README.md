This project simulates live football betting markets, processes historical odds data, and visualizes performance trends using smoothing algorithms and dynamic trading logic. It’s designed to model how a strategy might behave in real-time, where odds shift rapidly and decisions must be made incrementally

Features

Dynamic smoothing using Exponential Moving Average (EMA)

Realistic simulations that avoid future-look bias

Parameter optimization via multi-core sweeps

Real-time monitoring through websockets

Visualization of raw vs. smoothed market odds

Setup

1. Clone the repository

2. Create and activate a virtual environment

3. Install Dependencies
    - pip install -r requirements.txt

4. Paste your private key from kalshi into private_key.pem and paste your API key into the ACCESS_KEY of moniter_games 

5. For Only Running live simulation skip to step 9/ If you want to load past data continue

6. Run get_all_data.py to get the past data loaded into the games folder

7. Then Run Filter to filter the data into weeks and run based only get the game time data

8. At this point you have your data to work with in your filter folder you can see how the other programs work below

9. For live data run moniter_games and the active_games folder should start to fill up

10. run live_simulate to see your strategy in action keep in mind this will only work during live NFL games


Programs

get_all_data.py

The get_all_data fetches historical data from kalshi and puts it into the games folder in no particulare order

filter.py

The Filter program filters the data into weeks and shortens the data of each file to only contain in game odds.

create_graphs.py

This uses a smoothing algorithm to smooth out the odds of each game and puts each game into the graphs folder showing raw in gray and smoothed in blue. The smoothing can be adjusted with the alpha variable.

advanced_simulate.py

This is a model strategy that buys both teams at the beggining and sells depending on certain variables

super_checker_full.py

This runs a parameter sweep for each variable testing every combination possible within of the variables the system (start, stop, step) is used for each variable

moniter_games.py

This uses an API key to get live data from the acitive games updating each second and adding the games to the active_games folder.

simulate_live.py

Currently uses the strategy in advanced simulate to determine buys and sells and displays current positions in the terminal.