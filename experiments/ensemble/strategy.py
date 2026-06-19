"""
Experiment 3: Ensemble Voting Strategy
Runs multiple sub-strategies simultaneously. Only trades when >= MIN_VOTES agree.
Reduces false signals by requiring multi-strategy confluence.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import talib
import numpy as np
from config_practice import *

NAME = "ensemble"
MIN_VOTES = 2  # minimum strategies that must agree

STRATEGIES = {}  # populated at runtime

def register(strategy_func, name):
    STRATEGIES[name] = strategy_func

def market_structure_strategy(api, asset, candles):
    """Simplified market structure logic for ensemble"""
    if len(candles) < 50:
        return None, 0.0
    
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    
    # Detect swing highs/lows
    swing_highs = []
    swing_lows = []
    for i in range(2, len(closes)-2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append((i, highs[i]))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append((i, lows[i]))
    
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None, 0.0
    
    last = closes[-1]
    near_swing_high = any(abs(last - sh[1]) / sh[1] < 0.001 for sh in swing_highs[-3:])
    near_swing_low = any(abs(last - sl[1]) / sl[1] < 0.001 for sl in swing_lows[-3:])
    
    # Check for break of structure
    last_swing_high = swing_highs[-1][1]
    last_swing_low = swing_lows[-1][1]
    
    if last > last_swing_high and closes[-2] <= last_swing_high:
        return "call", 70.0  # Bullish BOS
    elif last < last_swing_low and closes[-2] >= last_swing_low:
        return "put", 70.0  # Bearish BOS
    elif near_swing_low and closes[-1] > closes[-2] and closes[-2] > closes[-3]:
        return "call", 55.0  # Bounce from support
    elif near_swing_high and closes[-1] < closes[-2] and closes[-2] < closes[-3]:
        return "put", 55.0  # Rejection at resistance
    
    return None, 0.0

def rsi_adx_strategy(api, asset, candles):
    """Simplified RSI/ADX logic for ensemble"""
    if len(candles) < 30:
        return None, 0.0
    
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    
    rsi = talib.RSI(closes, timeperiod=14)
    adx = talib.ADX(highs, lows, closes, timeperiod=14)
    
    if np.isnan(rsi[-1]) or np.isnan(adx[-1]):
        return None, 0.0
    
    if rsi[-1] < 30 and adx[-1] > 25:
        return "call", 65.0
    elif rsi[-1] > 70 and adx[-1] > 25:
        return "put", 65.0
    elif rsi[-1] < 40 and rsi[-1] > rsi[-2] and adx[-1] > 20:
        return "call", 50.0
    elif rsi[-1] > 60 and rsi[-1] < rsi[-2] and adx[-1] > 20:
        return "put", 50.0
    
    return None, 0.0

def macd_strategy(api, asset, candles):
    """MACD crossover strategy"""
    if len(candles) < 35:
        return None, 0.0
    
    closes = np.array([c['close'] for c in candles], dtype=float)
    
    macd, signal, hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
    
    if np.isnan(macd[-1]) or np.isnan(signal[-1]) or np.isnan(hist[-1]):
        return None, 0.0
    
    # MACD crossover
    if hist[-1] > 0 and hist[-2] <= 0:
        return "call", 60.0
    elif hist[-1] < 0 and hist[-2] >= 0:
        return "put", 60.0
    
    # MACD divergence (simplified)
    if len(candles) > 60:
        price_lower = closes[-1] < closes[-20]
        macd_higher = macd[-1] > macd[-20]
        if price_lower and macd_higher and hist[-1] > 0:
            return "call", 55.0  # Bullish divergence
        price_higher = closes[-1] > closes[-20]
        macd_lower = macd[-1] < macd[-20]
        if price_higher and macd_lower and hist[-1] < 0:
            return "put", 55.0  # Bearish divergence
    
    return None, 0.0

# Register all sub-strategies
register(market_structure_strategy, "market_structure")
register(rsi_adx_strategy, "rsi_adx")
register(macd_strategy, "macd")

def analyze(api, asset, candles):
    """
    Run all registered strategies and vote on direction.
    Returns (direction, confidence) if enough votes, else (None, 0)
    """
    call_votes = 0
    put_votes = 0
    total_confidence = 0.0
    results = {}
    
    for name, func in STRATEGIES.items():
        try:
            direction, confidence = func(api, asset, candles)
            results[name] = (direction, confidence)
            if direction == "call":
                call_votes += 1
                total_confidence += confidence
            elif direction == "put":
                put_votes += 1
                total_confidence += confidence
        except Exception as e:
            pass
    
    total_votes = call_votes + put_votes
    
    if total_votes < MIN_VOTES:
        return None, 0.0
    
    if call_votes > put_votes:
        confidence = min(99.0, total_confidence / call_votes + (call_votes - put_votes) * 10)
        return "call", confidence
    elif put_votes > call_votes:
        confidence = min(99.0, total_confidence / put_votes + (put_votes - call_votes) * 10)
        return "put", confidence
    
    return None, 0.0
