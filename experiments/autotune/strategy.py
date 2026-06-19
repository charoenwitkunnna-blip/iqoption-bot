#!/usr/bin/env python3
"""
Experiment 9: AutoTune — Continuous per-asset parameter optimization + approval system.
Mirrors the real bot's winning logic exactly.
"""
import sys, os, json, time, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import pandas as pd
import pandas_ta as ta

NAME = "AUTO-TUNE"
MIN_CONFIDENCE = 65
MIN_REQUIRED_WR = 0.70

# Per-asset approved models cache
approved_models = {}  # asset -> {fast, slow, adx, wr, updated_at}

def run_optimization(api, asset):
    """Brute-force parameter sweep to find best parameters (mirrors run_parameter_tuning_sweep)"""
    try:
        candles = api.get_candles(asset, 60, 120, time.time())
        if not candles or len(candles) < 100:
            return None
        
        df = pd.DataFrame(candles)
        close = df['close']
        high = df['max']
        low = df['min']
        
        # Try all combo variants
        best_wr = 0
        best_params = None
        
        fast_opts = [3, 5, 7]
        slow_opts = [10, 14, 21]
        adx_opts = [10, 14, 20]
        
        for fast_len in fast_opts:
            for slow_len in slow_opts:
                if fast_len >= slow_len:
                    continue
                for adx_len in adx_opts:
                    # Calculate signals using these parameters
                    adx_df = ta.adx(high, low, close, length=adx_len)
                    if adx_df is None or adx_df.empty:
                        continue
                    adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
                    adx_series = adx_df[adx_col]
                    
                    fast_rsi = ta.rsi(close, length=fast_len)
                    slow_rsi = ta.rsi(close, length=slow_len)
                    if fast_rsi is None or slow_rsi is None:
                        continue
                    
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
                    
                    # Simulate trading
                    wins = 0
                    total = 0
                    for i in range(21, len(signals) - 2):
                        if signals[i] == "call":
                            total += 1
                            if close.iloc[i+2] > close.iloc[i+1]:
                                wins += 1
                        elif signals[i] == "put":
                            total += 1
                            if close.iloc[i+2] < close.iloc[i+1]:
                                wins += 1
                    
                    if total >= 10:
                        wr = wins / total
                        if wr > best_wr:
                            best_wr = wr
                            best_params = {
                                'FAST_RSI': fast_len,
                                'SLOW_RSI': slow_len,
                                'ADX': adx_len,
                                'WR': wr,
                                'trades': total
                            }
        
        return best_params
    except:
        return None

def analyze(api, asset, candles):
    """Analyze with per-asset optimized parameters"""
    # First check if we have approved model
    model = approved_models.get(asset)
    
    # If model is stale (no update in last 5 min), re-optimize
    if not model or (time.time() - model['updated_at']) > 300:
        result = run_optimization(api, asset)
        if result and result['WR'] >= MIN_REQUIRED_WR:
            approved_models[asset] = {
                'fast': result['FAST_RSI'],
                'slow': result['SLOW_RSI'],
                'adx': result['ADX'],
                'wr': result['WR'],
                'updated_at': time.time()
            }
        elif result:
            # Store but don't approve
            approved_models[asset] = {
                'fast': result['FAST_RSI'],
                'slow': result['SLOW_RSI'],
                'adx': result['ADX'],
                'wr': result['WR'],
                'updated_at': time.time()
            }
    
    model = approved_models.get(asset)
    if not model or model.get('wr', 0) < MIN_REQUIRED_WR:
        return None, 0  # Not approved
    
    df = pd.DataFrame(candles)
    if df.empty or len(df) < 55:
        return None, 0
    
    close = df['close']
    high = df['max']
    low = df['min']
    
    # HTF trend filter
    ema50 = ta.ema(close, length=50)
    if ema50 is None or ema50.empty or pd.isna(ema50.iloc[-1]):
        return None, 0
    htf_bull = close.iloc[-1] > ema50.iloc[-1]
    htf_bear = close.iloc[-1] < ema50.iloc[-1]
    
    # Calculate with optimized params
    adx_df = ta.adx(high, low, close, length=model['adx'])
    if adx_df is None or adx_df.empty:
        return None, 0
    adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
    
    fast_rsi = ta.rsi(close, length=model['fast'])
    slow_rsi = ta.rsi(close, length=model['slow'])
    if fast_rsi is None or slow_rsi is None:
        return None, 0
    
    adx_series = adx_df[adx_col]
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
        conf = 65 + int(model['wr'] * 25)
        return "call", min(95, conf)
    elif last_signal == "put" and htf_bear:
        conf = 65 + int(model['wr'] * 25)
        return "put", min(95, conf)
    
    return None, 0
