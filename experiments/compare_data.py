#!/usr/bin/env python3
"""Compare PRACTICE vs REAL candle data for the same asset/time"""
import sys, time
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()

# Get PRACTICE balance candles
api.change_balance("PRACTICE")
time.sleep(1)
practice_candles = api.get_candles("EURUSD-OTC", 60, 10, time.time())
practice_close = [c['close'] for c in practice_candles] if practice_candles else []
print(f"PRACTICE (EURUSD-OTC): {[f'{c:.5f}' for c in practice_close]}")

# Get REAL balance candles
api.change_balance("REAL")
time.sleep(1) 
real_candles = api.get_candles("EURUSD-OTC", 60, 10, time.time())
real_close = [c['close'] for c in real_candles] if real_candles else []
print(f"REAL    (EURUSD-OTC): {[f'{c:.5f}' for c in real_close]}")

# Compare
match = practice_close == real_close
print(f"Candles match: {match}")
if not match and practice_close and real_close:
    print(f"Difference: {[round(abs(p-r), 5) for p, r in zip(practice_close, real_close)][:5]}")

# Check balance
api.change_balance("PRACTICE")
time.sleep(1)
print(f"PRACTICE balance: {api.get_balance()}")
api.change_balance("REAL")  
time.sleep(1)
print(f"REAL balance: {api.get_balance()}")
