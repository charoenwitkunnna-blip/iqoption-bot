"""
RHO CALL TEST — Same as rho_bounce but CALL only.
Testing if support bounces work (was 2W/5L = 29% on tiny sample).
"""
NAME = "rho_call_test"

import numpy as np


def find_swing_highs(highs, lookback=6):
    swings = []
    for i in range(lookback, len(highs) - lookback):
        left = highs[i - lookback:i]
        right = highs[i + 1:i + lookback + 1]
        if highs[i] > np.max(left) and highs[i] > np.max(right):
            swings.append((i, highs[i]))
    return swings


def find_swing_lows(lows, lookback=6):
    swings = []
    for i in range(lookback, len(lows) - lookback):
        left = lows[i - lookback:i]
        right = lows[i + 1:i + lookback + 1]
        if lows[i] < np.min(left) and lows[i] < np.min(right):
            swings.append((i, lows[i]))
    return swings


def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n)
    pd = np.zeros(n)
    nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1]))
        u = highs[i] - highs[i-1]
        d = lows[i-1] - lows[i]
        pd[i] = u if (u > d and u > 0) else 0
        nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n)
    ps = np.zeros(n)
    ns = np.zeros(n)
    ts[period] = sum(tr[1:period + 1])
    ps[period] = sum(pd[1:period + 1])
    ns[period] = sum(nd[1:period + 1])
    for i in range(period + 1, n):
        ts[i] = ts[i-1] - ts[i-1] / period + tr[i]
        ps[i] = ps[i-1] - ps[i-1] / period + pd[i]
        ns[i] = ns[i-1] - ns[i-1] / period + nd[i]
    pi = np.zeros(n)
    ni = np.zeros(n)
    dx = np.zeros(n)
    ax = np.zeros(n)
    for i in range(period + 1, n):
        if ts[i] > 0:
            pi[i] = 100 * ps[i] / ts[i]
            ni[i] = 100 * ns[i] / ts[i]
        if pi[i] + ni[i] > 0:
            dx[i] = 100 * abs(pi[i] - ni[i]) / (pi[i] + ni[i])
    ax[period * 2] = np.mean(dx[period + 1:period * 2 + 1])
    for i in range(period * 2 + 1, n):
        ax[i] = (ax[i - 1] * (period - 1) + dx[i]) / period
    return ax[-1]


def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    if len(closes) < 25:
        return None, 0

    # ADX < 25 (ranging market)
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 25:
        return None, 0

    # lookback=3 for swing lows (support levels)
    lookback = 3
    search_l = lows[-20:-2]
    swing_lows = find_swing_lows(search_l, lookback)

    if not swing_lows:
        return None, 0

    cur_close = closes[-1]
    cur_low = lows[-1]
    cur_high = highs[-1]
    prev_close = closes[-2]
    cur_body = cur_close - opens[-1]
    prev_body = prev_close - opens[-2]
    total_range = cur_high - cur_low

    if total_range <= 0:
        return None, 0

    lower_wick = (min(cur_close, opens[-1]) - cur_low) / total_range

    # === SUPPORT BOUNCE — CALL only ===
    for idx, level in swing_lows:
        age = len(candles) - 20 + idx
        if age < 2:
            continue

        dist_pct = abs(cur_close - level) / cur_close * 100
        if dist_pct > 0.15:
            continue

        if cur_close > level * 0.999:
            if cur_body > 0:  # Bullish candle
                if total_range > 0 and lower_wick > 0.45:
                    if prev_body > 0:
                        return "call", 70
                    return "call", 60

    return None, 0
