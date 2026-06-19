#!/usr/bin/env python3
"""Test different breakout and MA crossover strategies"""
import sys, os, numpy as np
import pandas as pd
import pandas_ta as ta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

NAME = "simple_strategies"

STRATEGY_MODE = "bb_bounce"  # Can be "breakout", "ma_crossover", "bb_bounce", "ema_trend"

def analyze(api, asset, candles):
    if not candles or len(candles) < 30:
        return None
    
    df = pd.DataFrame(candles)
    close = df['close'].values
    high = df['max'].values
    low = df['min'].values
    
    ### STRATEGY 1: Breakout ###
    if STRATEGY_MODE == "breakout":
        # Break above recent 5-candle high = CALL
        recent_high = max(high[-6:-1])  # high of last 5 candles (exclude current)
        recent_low = min(low[-6:-1])    # low of last 5 candles
        current_close = close[-1]
        
        # Price broke above range = CALL
        if current_close > recent_high:
            return "call", 65
        # Price broke below range = PUT
        elif current_close < recent_low:
            return "put", 65
        return None
    
    ### STRATEGY 2: MA Crossover ###
    elif STRATEGY_MODE == "ma_crossover":
        close_s = pd.Series(close)
        ema5 = ta.ema(close_s, length=5)
        ema10 = ta.ema(close_s, length=10)
        if ema5 is None or ema10 is None or len(ema5) < 2:
            return None
        # Cross up
        if ema5.iloc[-2] <= ema10.iloc[-2] and ema5.iloc[-1] > ema10.iloc[-1]:
            return "call", 65
        # Cross down
        elif ema5.iloc[-2] >= ema10.iloc[-2] and ema5.iloc[-1] < ema10.iloc[-1]:
            return "put", 65
        return None
    
    ### STRATEGY 3: BB Bounce ###
    elif STRATEGY_MODE == "bb_bounce":
        close_s = pd.Series(close)
        bb = ta.bbands(close_s, length=20, std=2)
        if bb is None or bb.empty:
            return None
        bb_lower = bb.iloc[:, 0]
        bb_upper = bb.iloc[:, 2]
        if len(bb_lower) < 2:
            return None
        current = close[-1]
        # Touch lower band = CALL
        if current <= bb_lower.iloc[-1] * 1.001:
            return "call", 70
        # Touch upper band = PUT
        elif current >= bb_upper.iloc[-1] * 0.999:
            return "put", 70
        return None
    
    ### STRATEGY 4: EMA Trend Follow ###
    elif STRATEGY_MODE == "ema_trend":
        close_s = pd.Series(close)
        ema20 = ta.ema(close_s, length=20)
        ema50 = ta.ema(close_s, length=50)
        if ema20 is None or ema50 is None or len(ema20) < 2:
            return None
        # Price above both EMAs = bullish trend
        if close[-1] > ema20.iloc[-1] > ema50.iloc[-1]:
            # Pullback to EMA20 = CALL
            if close[-2] <= ema20.iloc[-2] and close[-1] > ema20.iloc[-1]:
                return "call", 70
        # Price below both EMAs = bearish trend
        elif close[-1] < ema20.iloc[-1] < ema50.iloc[-1]:
            # Pullback to EMA20 = PUT
            if close[-2] >= ema20.iloc[-2] and close[-1] < ema20.iloc[-1]:
                return "put", 70
        return None
    
    return None
