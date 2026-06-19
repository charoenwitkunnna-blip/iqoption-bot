#!/usr/bin/env python3
"""Quick test of replica_exact analyze with fixed runner handling"""
import sys, time, importlib
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance(BALANCE_TYPE)
balance = api.get_balance()
print(f"Connected. Balance: {balance}")

# Load strategy
spec = importlib.util.spec_from_file_location("replica_exact", "/root/iqoption-bot/experiments/replica_exact/strategy.py")
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)

# Test one asset
asset = "EURUSD-OTC"
candles = api.get_candles(asset, 60, 250, time.time())
print(f"Got {len(candles)} candles for {asset}")

direction = strat.analyze(api, asset, candles)
print(f"Direction type: {type(direction).__name__} value: {direction}")

if isinstance(direction, (tuple, list)):
    direction, confidence = direction[0], direction[1] if len(direction) > 1 else 50
else:
    confidence = 50
    
print(f"Result: dir={direction} conf={confidence}")
