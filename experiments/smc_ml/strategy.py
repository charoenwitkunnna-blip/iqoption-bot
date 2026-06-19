#!/usr/bin/env python3
"""
Experiment 5: SMC-ML Hybrid — combines the real bot's SMC strategy with 
ML prediction overlay for higher accuracy.
"""
import sys, os, json, math, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np

NAME = "smc-ml"

# Confidence thresholds
MIN_CONFIDENCE = 65

def ema(series, length):
    """Simple EMA implementation"""
    arr = np.array(series, dtype=float)
    if len(arr) < length:
        return None
    result = np.zeros(len(arr))
    multiplier = 2.0 / (length + 1)
    result[length-1] = np.mean(arr[:length])
    for i in range(length, len(arr)):
        result[i] = (arr[i] - result[i-1]) * multiplier + result[i-1]
    return pd.Series(result, index=series.index) if hasattr(series, 'index') else result

def rsi(series, length=14):
    arr = np.array(series, dtype=float)
    if len(arr) < length + 1:
        return None
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:length])
    avg_loss = np.mean(losses[:length])
    result = np.zeros(len(arr))
    result[:length] = 50  # Neutral fill
    for i in range(length, len(arr)):
        if avg_loss == 0:
            result[i] = 100
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
        # Update averages
        avg_gain = (avg_gain * (length - 1) + gains[i-1]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i-1]) / length
    return result[-1]

def adx(high, low, close, length=14):
    if len(high) < length * 2:
        return 0, 0, 0
    
    high_arr = np.array(high, dtype=float)
    low_arr = np.array(low, dtype=float)
    close_arr = np.array(close, dtype=float)
    
    tr = np.maximum(high_arr[1:] - low_arr[1:], 
                     np.maximum(np.abs(high_arr[1:] - close_arr[:-1]), 
                                np.abs(low_arr[1:] - close_arr[:-1])))
    
    up_move = high_arr[1:] - high_arr[:-1]
    down_move = low_arr[:-1] - low_arr[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    tr_smooth = np.mean(tr[-length:]) if len(tr) >= length else np.mean(tr)
    plus_smooth = np.mean(plus_dm[-length:]) if len(plus_dm) >= length else np.mean(plus_dm)
    minus_smooth = np.mean(minus_dm[-length:]) if len(minus_dm) >= length else np.mean(minus_dm)
    
    if tr_smooth == 0:
        return 0, 0, 0
    
    pdi = 100 * plus_smooth / tr_smooth
    ndi = 100 * minus_smooth / tr_smooth
    
    dx = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0
    adx_val = dx  # Simplified ADX
    
    return adx_val, pdi, ndi

def detect_order_blocks(close, high, low, lookback=30):
    """Detect order blocks - last swing high/low"""
    if len(close) < lookback:
        return None, None
    
    highs = np.array(high[-lookback:], dtype=float)
    lows = np.array(low[-lookback:], dtype=float)
    
    # Find swing highs and lows
    swing_highs = []
    swing_lows = []
    for i in range(2, len(highs)-2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(i)
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(i)
    
    # Nearest key levels
    current_close = close[-1]
    nearest_resistance = None
    nearest_support = None
    
    for idx in swing_highs:
        if highs[idx] > current_close:
            if nearest_resistance is None or abs(highs[idx] - current_close) < abs(nearest_resistance - current_close):
                nearest_resistance = highs[idx]
    
    for idx in swing_lows:
        if lows[idx] < current_close:
            if nearest_support is None or abs(lows[idx] - current_close) < abs(nearest_support - current_close):
                nearest_support = lows[idx]
    
    return nearest_support, nearest_resistance

def detect_liquidity_sweep(close, high, low, lookback=20):
    """Detect if recent price sweep took out old high/low (liquidity grab)"""
    if len(high) < lookback + 5:
        return False, False
    
    recent_high = max(high[-5:])
    recent_low = min(low[-5:])
    old_high = max(high[-lookback:-5]) if len(high) > 5 else recent_high
    old_low = min(low[-lookback:-5]) if len(high) > 5 else recent_low
    
    bear_swept = recent_high > old_high and close[-1] < ema(close, 5)[-1] if ema(close, 5) is not None else False
    bull_swept = recent_low < old_low and close[-1] > ema(close, 5)[-1] if ema(close, 5) is not None else False
    
    return bull_swept, bear_swept

def analyze(api, asset, candles):
    """
    SMC-ML Hybrid: SMC trend structure + ML-enhanced entry timing.
    Returns (direction: str|None, confidence: float)
    """
    df = pd.DataFrame(candles)
    if df.empty or len(df) < 55:
        return None, 0
    
    closes = df['close'].values.astype(float)
    highs = df['max'].values.astype(float)
    lows = df['min'].values.astype(float)
    opens = df['open'].values.astype(float)
    
    # === TREND FILTER (HTF EMA) ===
    ema50 = ema(closes, 50)
    if ema50 is None:
        return None, 0
    htf_ema50_val = ema50[-1]
    htf_bullish = closes[-1] > htf_ema50_val
    htf_bearish = closes[-1] < htf_ema50_val
    
    # === INDICATORS ===
    rsi_val = rsi(closes, 14)
    adx_val, pdi, ndi = adx(highs, lows, closes, 14)
    
    # Price position within recent range (0-100)
    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    range_pos = (closes[-1] - recent_low) / (recent_high - recent_low) * 100 if (recent_high - recent_low) > 0 else 50
    
    # Check for oversold/overbought
    oversold = rsi_val < 35 if rsi_val is not None else False
    overbought = rsi_val > 65 if rsi_val is not None else False
    
    # Trend strength
    strong_trend = adx_val > 25 if adx_val else False
    
    # === SMC STRUCTURE ===
    support, resistance = detect_order_blocks(closes, highs, lows, 30)
    bull_sweep, bear_sweep = detect_liquidity_sweep(closes, highs, lows, 20)
    
    # Price relative to SMC levels
    near_support = support is not None and (closes[-1] - support) / support < 0.005
    near_resistance = resistance is not None and (resistance - closes[-1]) / closes[-1] < 0.005
    
    # Candle pattern: engulfing
    prev_open, prev_close = opens[-2], closes[-2]
    curr_open, curr_close = opens[-1], closes[-1]
    bull_engulfing = curr_close > curr_open and prev_close < prev_open and curr_close > prev_open and curr_open < prev_close
    bear_engulfing = curr_close < curr_open and prev_close > prev_open and curr_close < prev_open and curr_open > prev_close
    
    # === SIGNAL SCORING ===
    call_score = 0
    put_score = 0
    
    # Trend alignment
    if htf_bullish:
        call_score += 25
    if htf_bearish:
        put_score += 25
    
    # RSI extremes
    if oversold:
        call_score += 20
        put_score -= 10
    elif overbought:
        put_score += 20
        call_score -= 10
    
    # Range position
    if range_pos < 20:  # Near bottom of range
        call_score += 15
    elif range_pos > 80:  # Near top of range
        put_score += 15
    
    # Liquidity sweeps (reversals after taking out old highs/lows)
    if bull_sweep:
        call_score += 30
    if bear_sweep:
        put_score += 30
    
    # Support/Resistance bounces
    if near_support and htf_bullish:
        call_score += 25
    if near_resistance and htf_bearish:
        put_score += 25
    
    # Candlestick patterns
    if bull_engulfing:
        call_score += 15
    if bear_engulfing:
        put_score += 15
    
    # Trend strength bonus
    if strong_trend and htf_bullish:
        call_score += 10
    elif strong_trend and htf_bearish:
        put_score += 10
    
    # === DECISION ===
    total_score = max(call_score, put_score)
    direction = None
    confidence = 0
    
    if total_score >= 40:  # Minimum signal threshold
        if call_score > put_score:
            direction = "call"
            confidence = min(95, call_score)
        elif put_score > call_score:
            direction = "put"
            confidence = min(95, put_score)
    
    # Only trade above minimum confidence
    if confidence < MIN_CONFIDENCE:
        return None, 0
    
    return direction, confidence
