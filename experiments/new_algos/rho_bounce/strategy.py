"""
RHO BOUNCE — Original config. PUT only, ADX<25, lookback=5, wick>0.5, dist<0.2%
"""
NAME = "rho_bounce"
import numpy as np

def find_swing_highs(highs, lookback=5):
    swings = []
    for i in range(lookback, len(highs) - lookback):
        left = highs[i - lookback:i]
        right = highs[i + 1:i + lookback + 1]
        if highs[i] > np.max(left) and highs[i] > np.max(right):
            swings.append((i, highs[i]))
    return swings

def adx(highs, lows, closes, period=14):
    if len(closes) < period + 1: return None
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    plus_dm = np.where((highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]), np.maximum(highs[1:] - highs[:-1], 0), 0)
    minus_dm = np.where((lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]), np.maximum(lows[:-1] - lows[1:], 0), 0)
    atr = np.convolve(tr, np.ones(period)/period, mode='valid')
    plus_di = 100 * np.convolve(plus_dm, np.ones(period)/period, mode='valid') / (atr + 1e-10)
    minus_di = 100 * np.convolve(minus_dm, np.ones(period)/period, mode='valid') / (atr + 1e-10)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx_val = np.convolve(dx, np.ones(period)/period, mode='valid')
    return adx_val[-1] if len(adx_val) > 0 else None

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)
    if len(closes) < 30: return None, 0
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 25: return None, 0
    lookback = 5
    search = highs[-20:-2]
    swing_highs = find_swing_highs(search, lookback)
    if not swing_highs: return None, 0
    cur_close = closes[-1]
    cur_high = highs[-1]
    cur_low = lows[-1]
    prev_close = closes[-2]
    cur_body = cur_close - opens[-1]
    prev_body = prev_close - opens[-2]
    total_range = cur_high - cur_low
    if total_range <= 0: return None, 0
    upper_wick = (cur_high - max(cur_close, opens[-1])) / total_range
    for idx, level in swing_highs:
        age = len(candles) - 20 + idx
        if age < 2: continue
        dist_pct = abs(cur_close - level) / cur_close * 100
        if dist_pct > 0.2: continue
        if cur_close < level * 1.001:
            if cur_body < 0:
                if total_range > 0 and upper_wick > 0.5:
                    if prev_body < 0:
                        return "put", 70
    return None, 0
