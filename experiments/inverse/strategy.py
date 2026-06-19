#!/usr/bin/env python3
"""
Experiment 7: Inverse Strategy — does the OPPOSITE of the V2 scoring signals.
If V2 was consistently wrong, the inverse should be consistently right.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import pandas as pd
import pandas_ta as ta

NAME = "INVERSE"
MIN_CONFIDENCE = 50

def analyze(api, asset, candles):
    """Do the opposite of what V2 would do"""
    df = pd.DataFrame(candles)
    if df.empty or len(df) < 55:
        return None, 0
    
    close = df['close']
    high = df['max']
    low = df['min']
    
    # Same indicators as V2
    rsi_val = ta.rsi(close, length=14)
    adx_df = ta.adx(high, low, close, length=14)
    bb = ta.bbands(close, length=20, std=2)
    macd = ta.macd(close)
    
    if any(x is None or x.empty for x in [rsi_val, adx_df, bb, macd]):
        return None, 0
    
    adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
    adx_val = adx_df[adx_col]
    bb_lower = bb.iloc[:,0]
    bb_upper = bb.iloc[:,2]
    macd_line = macd.iloc[:,0]
    macd_signal = macd.iloc[:,1]
    
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    bull_engulf = last_candle['close'] > last_candle['open'] and prev_candle['close'] < prev_candle['open'] and last_candle['close'] > prev_candle['open'] and last_candle['open'] < prev_candle['close']
    bear_engulf = last_candle['close'] < last_candle['open'] and prev_candle['close'] > prev_candle['open'] and last_candle['close'] < prev_candle['open'] and last_candle['open'] > prev_candle['close']
    
    near_bb_lower = not pd.isna(bb_lower.iloc[-1]) and last_candle['close'] < bb_lower.iloc[-1] * 1.005
    near_bb_upper = not pd.isna(bb_upper.iloc[-1]) and last_candle['close'] > bb_upper.iloc[-1] * 0.995
    
    macd_cross_up = not pd.isna(macd_line.iloc[-2]) and not pd.isna(macd_signal.iloc[-2]) and macd_line.iloc[-2] <= macd_signal.iloc[-2] and macd_line.iloc[-1] > macd_signal.iloc[-1]
    macd_cross_dn = not pd.isna(macd_line.iloc[-2]) and not pd.isna(macd_signal.iloc[-2]) and macd_line.iloc[-2] >= macd_signal.iloc[-2] and macd_line.iloc[-1] < macd_signal.iloc[-1]
    
    # INVERSE logic: do what V2 wouldn't
    call_score = 0
    put_score = 0
    
    # V2 would short overbought, we buy overbought (follow trend)
    if not pd.isna(rsi_val.iloc[-1]) and rsi_val.iloc[-1] > 65:
        call_score += 25  # INVERSE: buy when overbought (trend continuation)
    if not pd.isna(rsi_val.iloc[-1]) and rsi_val.iloc[-1] < 35:
        put_score += 25   # INVERSE: sell when oversold
    
    # V2 bounces from BB, we break BB
    if near_bb_upper:
        call_score += 25  # INVERSE: buy when breaking above upper BB
    if near_bb_lower:
        put_score += 25   # INVERSE: sell when breaking below lower BB
    
    # V2 does MACD crossover, we do the opposite
    if macd_cross_up:
        put_score += 20
    if macd_cross_dn:
        call_score += 20
    
    # V2 looks for reversals, we follow the move
    if bull_engulf:
        call_score += 20
    if bear_engulf:
        put_score += 20
    
    # Follow ADX trend direction
    if not pd.isna(adx_val.iloc[-1]) and adx_val.iloc[-1] > 25:
        pdi = adx_df.iloc[-1, 1]  # +DI
        ndi = adx_df.iloc[-1, 2]  # -DI
        if isinstance(pdi, (int, float)) and isinstance(ndi, (int, float)):
            if pdi > ndi:
                call_score += 15  # Strong uptrend, buy
            else:
                put_score += 15   # Strong downtrend, sell
    
    total = max(call_score, put_score)
    if total < 30:
        return None, 0
    
    direction = None
    conf = 0
    if call_score > put_score:
        direction = "call"
        conf = min(95, 50 + call_score // 2)
    elif put_score > call_score:
        direction = "put"
        conf = min(95, 50 + put_score // 2)
    
    return direction, conf
