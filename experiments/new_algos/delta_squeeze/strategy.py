"""
DELTA SQUEEZE — Bollinger Band Contraction → Breakout
=======================================================
When BB width hits a 20-period low, a breakout is imminent.
Enter on the first candle that closes outside the bands.
"""
NAME = "delta_squeeze"

import numpy as np

def ema(data, period):
    if len(data) < period: return None
    a = 2.0/(period+1.0)
    r = np.zeros(len(data)); r[0]=data[0]
    for i in range(1,len(data)): r[i]=a*data[i]+(1-a)*r[i-1]
    return r

def rsi(data, period=14):
    if len(data) < period+1: return None
    d = np.diff(data)
    g = np.where(d>0,d,0); l = np.where(d<0,-d,0)
    ag = np.mean(g[:period]); al = np.mean(l[:period])
    if al==0: return 100
    return 100-(100/(1+ag/al))

def bollinger_bands(data, period=20, mult=2.0):
    if len(data) < period: return None,None,None
    idx = np.arange(period-1, len(data))
    window = np.lib.stride_tricks.sliding_window_view(data, period)
    sma = np.mean(window, axis=1)
    std = np.std(window, axis=1)
    return sma + mult*std, sma, sma - mult*std

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 25: return None,0

    upper, mid, lower = bollinger_bands(closes, 20, 2.0)
    if upper is None: return None,0

    # BB width = (upper - lower) / mid
    bb_width = (upper - lower) / mid

    # Detect squeeze: current width is lowest in last 20 periods
    if len(bb_width) < 20: return None,0
    width_min_20 = np.min(bb_width[-21:-1])
    width_now = bb_width[-1]

    is_squeeze = width_now <= width_min_20 * 1.05  # within 5% of 20-period low

    if not is_squeeze: return None,0

    # Check for breakout
    cur_close = closes[-1]
    cur_upper = upper[-1]
    cur_lower = lower[-1]
    prev_close = closes[-2]
    prev_upper = upper[-2]
    prev_lower = lower[-2]

    cur_rsi = rsi(closes, 9)

    # Breakout UP: first close above upper band
    if prev_close <= prev_upper and cur_close > cur_upper:
        if cur_rsi and cur_rsi > 50:
            return "call", 70
        return "call", 60

    # Breakout DOWN: first close below lower band
    if prev_close >= prev_lower and cur_close < cur_lower:
        if cur_rsi and cur_rsi < 50:
            return "put", 70
        return "put", 60

    return None,0
