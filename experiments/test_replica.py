#!/usr/bin/env python3
"""Quick test of the replica_exact strategy"""
import sys, time
sys.path.insert(0, '/root/iqoption-bot/experiments')

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance(BALANCE_TYPE)

# Get candles for a top asset  
candles = api.get_candles("EURUSD-OTC", 60, 250, time.time())
print(f"Got {len(candles)} candles")

from replica_exact.strategy import run_parameter_tuning_sweep, calculate_adaptive_regime_signals, analyze
import pandas as pd
import pandas_ta as ta

# Test tuning
params = run_parameter_tuning_sweep(candles)
print(f"Tuned params: {params}")

# Test analysis with tuned params
if params:
    df = pd.DataFrame(candles)
    analyzed = calculate_adaptive_regime_signals(
        df, params['FAST_RSI_LENGTH'], params['SLOW_RSI_LENGTH'], params['ADX_LENGTH']
    )
    if not analyzed.empty:
        last_sigs = analyzed[['composite_signal', 'adx', 'fast_rsi', 'slow_rsi']].tail(5)
        print("Last 5 signals:")
        print(last_sigs.to_string())

# Test HTF
htf = api.get_candles("EURUSD-OTC", 300, 60, time.time())
df_htf = pd.DataFrame(htf)
htf_ema50 = ta.ema(df_htf['close'], length=50)
htf_bullish = df_htf['close'].iloc[-1] > htf_ema50.iloc[-1]
htf_bearish = df_htf['close'].iloc[-1] < htf_ema50.iloc[-1]
print(f"Price: {df_htf['close'].iloc[-1]:.6f} EMA50: {htf_ema50.iloc[-1]:.6f} Bullish={htf_bullish} Bearish={htf_bearish}")

# Check 3 more assets for signals
for a in ["GBPUSD-OTC", "SP500-OTC", "XAUUSD-OTC"]:
    sig = analyze(api, a, api.get_candles(a, 60, 250, time.time()))
    print(f"{a}: {sig}")
    time.sleep(0.2)
