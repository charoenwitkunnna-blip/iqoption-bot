#!/usr/bin/env python3
"""Configuration for IQ Option Bot v2"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Credentials
IQ_OPTION_EMAIL = os.getenv("IQ_OPTION_EMAIL")
IQ_OPTION_PASSWORD = os.getenv("IQ_OPTION_PASSWORD")

# Account
BALANCE_TYPE = "REAL"  # REAL or PRACTICE
TRADE_AMOUNT = 30       # Base trade amount in THB

# Timeframes
TIMEFRAME = 60          # LTF: 1-minute candles (seconds)
HTF_TIMEFRAME = 300     # HTF: 5-minute candles (seconds)
EXPIRATION_MINS = 1     # Trade expiry in minutes

# Risk management
STOP_LOSS_LIMIT = 175   # Stop when PnL drops below -175 THB
POLL_INTERVAL = 10      # Seconds between scan cycles

# Scanning
MAX_SCAN_ASSETS = 10    # Top N assets to scan

# Parameter optimization
OPTIMIZATION_CANDLES = 500   # Candles to use for tuning
MIN_OPTIMIZATION_TRADES = 8  # Min trades to consider a parameter set
MIN_REQUIRED_WIN_RATE = 0.50 # Only trade assets with >= 50% simulated wr
OPTIMIZATION_INTERVAL = 600  # Retune every 600 seconds (10 min)
