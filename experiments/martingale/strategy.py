#!/usr/bin/env python3
"""
Experiment 8: Martingale Strategy — uses the winning replica's signal logic
but adds geometric progression recovery: double after loss, reset after win.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import pandas as pd
import pandas_ta as ta

NAME = "MARTINGALE"
MIN_CONFIDENCE = 60

BASE_AMOUNT = 5
MAX_STEP = 4  # Max double-downs: 5, 10, 20, 40 (recover losses + profit)
step = 0  # Current martingale step (tracked externally)

def calculate_signals(df, fast_len=7, slow_len=21, adx_len=14):
    close = df['close']
    high = df['max']
    low = df['min']
    
    ema50 = ta.ema(close, length=50)
    if ema50 is None or ema50.empty or pd.isna(ema50.iloc[-1]):
        return None
    
    htf_bull = close.iloc[-1] > ema50.iloc[-1]
    htf_bear = close.iloc[-1] < ema50.iloc[-1]
    
    adx_df = ta.adx(high, low, close, length=adx_len)
    if adx_df is None or adx_df.empty:
        return None, None
    
    adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
    adx_series = adx_df[adx_col]
    
    fast_rsi = ta.rsi(close, length=fast_len)
    slow_rsi = ta.rsi(close, length=slow_len)
    if fast_rsi is None or slow_rsi is None:
        return None, None
    
    regime = np.where(adx_series > 25, "trending", "ranging")
    signals = np.full(len(df), "neutral", dtype=object)
    
    is_ranging = (regime == "ranging")
    is_trending = (regime == "trending")
    
    fast_prev = fast_rsi.shift(1)
    slow_prev = slow_rsi.shift(1)
    cross_up = ((fast_prev <= slow_prev) & (fast_rsi > slow_rsi)).fillna(False)
    cross_dn = ((fast_prev >= slow_prev) & (fast_rsi < slow_rsi)).fillna(False)
    
    signals[is_ranging & (slow_rsi < 40) & cross_up] = "call"
    signals[is_ranging & (slow_rsi > 60) & cross_dn] = "put"
    signals[is_trending & (slow_rsi > 50) & cross_up] = "call"
    signals[is_trending & (slow_rsi < 50) & cross_dn] = "put"
    signals[np.arange(len(df)) < 20] = "neutral"
    
    last_signal = signals[-2]
    
    if last_signal == "call" and htf_bull:
        conf = 65
        if not pd.isna(slow_rsi.iloc[-2]) and slow_rsi.iloc[-2] < 35:
            conf += 10
        return "call", conf
    
    if last_signal == "put" and htf_bear:
        conf = 65
        if not pd.isna(slow_rsi.iloc[-2]) and slow_rsi.iloc[-2] > 65:
            conf += 10
        return "put", conf
    
    return None, 0

def calculate_amount():
    """Martingale step: BASE_AMOUNT * 2^step"""
    global step
    return BASE_AMOUNT * (2 ** min(step, MAX_STEP))

def on_win():
    global step
    step = 0  # Reset after win

def on_loss():
    global step
    step += 1  # Double down after loss

current_direction = None
current_confidence = 0

def analyze(api, asset, candles):
    global current_direction, current_confidence
    d, conf = calculate_signals(candles)
    current_direction = d
    current_confidence = conf
    return d, conf
