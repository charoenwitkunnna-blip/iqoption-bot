#!/usr/bin/env python3
"""
Experiment 6: Winning Strategy Replica (v2)
Uses pandas_ta for exact calculation parity with the real bot.
- Dual RSI crossover (fast/slow) with ADX regime filter
- HTF EMA50 trend filter
- Per-asset default parameters
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import pandas as pd
import pandas_ta as ta

NAME = "WINNING-REPLICA"
MIN_CONFIDENCE = 65

def analyze(api, asset, candles):
    """
    Exact replica of real bot's evaluate_smc_strategy + calculate_adaptive_regime_signals
    """
    df = pd.DataFrame(candles)
    if df.empty or len(df) < 55:
        return None, 0
    
    # HTF trend filter using EMA50
    ema50 = ta.ema(df['close'], length=50)
    if ema50 is None or ema50.empty or pd.isna(ema50.iloc[-1]):
        return None, 0
    
    htf_bullish = df['close'].iloc[-1] > ema50.iloc[-1]
    htf_bearish = df['close'].iloc[-1] < ema50.iloc[-1]
    
    # Default parameters (same as real bot)
    fast_rsi_len = 7
    slow_rsi_len = 21
    adx_len = 14
    
    # === SIGNAL GENERATION (exact copy of calculate_adaptive_regime_signals) ===
    close = df['close']
    high = df['max']
    low = df['min']
    
    # 1. ADX
    adx_df = ta.adx(high, low, close, length=adx_len)
    if adx_df is None or adx_df.empty:
        return None, 0
    adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
    adx_series = adx_df[adx_col]
    
    # 2. Dual RSI
    fast_rsi = ta.rsi(close, length=fast_rsi_len)
    slow_rsi = ta.rsi(close, length=slow_rsi_len)
    if fast_rsi is None or slow_rsi is None or fast_rsi.empty or slow_rsi.empty:
        return None, 0
    
    # 3. Vectorized signal generation
    regime = np.where(adx_series > 25, "trending", "ranging")
    signals = np.full(len(df), "neutral", dtype=object)
    
    is_ranging = (regime == "ranging")
    is_trending = (regime == "trending")
    
    fast_prev = fast_rsi.shift(1)
    slow_prev = slow_rsi.shift(1)
    cross_up = ((fast_prev <= slow_prev) & (fast_rsi > slow_rsi)).fillna(False)
    cross_dn = ((fast_prev >= slow_prev) & (fast_rsi < slow_rsi)).fillna(False)
    
    # Range conditions: mean reversion
    call_ranging = is_ranging & (slow_rsi < 40) & cross_up
    put_ranging = is_ranging & (slow_rsi > 60) & cross_dn
    
    # Trend conditions: momentum continuation
    call_trending = is_trending & (slow_rsi > 50) & cross_up
    put_trending = is_trending & (slow_rsi < 50) & cross_dn
    
    signals[call_ranging | call_trending] = "call"
    signals[put_ranging | put_trending] = "put"
    
    # Warmup: first 20 bars are neutral
    warmup = np.arange(len(df)) < 20
    signals[warmup] = "neutral"
    
    # === DECISION ===
    last_signal = signals[-2]  # Use second-to-last (most recent completed candle)
    
    if last_signal == "call" and htf_bullish:
        # Confidence: based on signal quality factors
        conf = 65
        slow_val = slow_rsi.iloc[-2] if not pd.isna(slow_rsi.iloc[-2]) else 50
        if slow_val < 35:
            conf += 10  # Stronger oversold bounce
        if adx_series.iloc[-2] > 25 if not pd.isna(adx_series.iloc[-2]) else False:
            conf += 10  # Trending momentum is stronger
        return "call", min(95, conf)
    
    elif last_signal == "put" and htf_bearish:
        conf = 65
        slow_val = slow_rsi.iloc[-2] if not pd.isna(slow_rsi.iloc[-2]) else 50
        if slow_val > 65:
            conf += 10
        if adx_series.iloc[-2] > 25 if not pd.isna(adx_series.iloc[-2]) else False:
            conf += 10
        return "put", min(95, conf)
    
    return None, 0
