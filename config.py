import os
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

IQ_OPTION_EMAIL = os.getenv("IQ_OPTION_EMAIL", "your_email@example.com")
IQ_OPTION_PASSWORD = os.getenv("IQ_OPTION_PASSWORD", "your_password_here")

# -----------------------------------------------------
# Trading Environment Parameters
# -----------------------------------------------------
TIMEFRAME = 60            # Lower Timeframe (LTF) candle size in seconds (1 minute)
HTF_TIMEFRAME = 900       # Higher Timeframe (HTF) candle size in seconds (15 minutes)
CANDLE_COUNT = 150        # Number of historical candles to warm up indicators safely
TRADE_AMOUNT = 30         # Amount per trade (minimum THB or currency equivalent)
EXPIRATION_MINS = 1       # Expiration duration in minutes for Turbo/Binary
POLL_INTERVAL = 5         # Seconds to sleep between scan loops
BALANCE_TYPE = "REAL" # "PRACTICE" or "REAL"
STOP_LOSS_LIMIT = 175.0   # Stop trading after losing 175 THB/USD in a session
MIN_PAYOUT_THRESHOLD = 0.80  # 80% Minimum payout threshold to execute a trade
MAX_SCAN_ASSETS = 10      # Max assets to stream and scan at one time (sorted by payout)

# -----------------------------------------------------
# Self-Tuning Optimization Parameters
# -----------------------------------------------------
OPTIMIZATION_INTERVAL = 300  # Run a self-tuning parameter sweep every 300s (5 minutes)
OPTIMIZATION_CANDLES = 200   # Number of historical candles to analyze during retuning
MIN_REQUIRED_WIN_RATE = 0.70 # Only allow trading on assets with a dynamic WR >= 70%
MIN_OPTIMIZATION_TRADES = 10 # Enforce a minimum of 10 simulated trades during parameter sweeps

DEFAULT_CONFIG = {
    'FAST_RSI_LENGTH': 5,
    'SLOW_RSI_LENGTH': 14,
    'ADX_LENGTH': 14,
    'simulated_wr': 0.0      # Defaults to 0% to prevent untrained trading
}
