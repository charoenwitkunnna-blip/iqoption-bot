"""
WICK HAMMER — Pure Wick Reversal Strategy
==========================================
Looks for exhaustion candles with long upper wicks.
No swing level detection — just pure candle anatomy.

Upper wick > 55% of range = sellers pushing back → PUT
Lower wick > 55% of range = buyers pushing back → CALL (disabled — CALL has 29% WR)

Works best in ranging markets (ADX < 25).
"""
NAME = "wick_hammer"

import numpy as np


def adx(highs, lows, closes, period=14):
    """Trend strength. Lower = ranging."""
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

    if len(closes) < 20:
        return None, 0

    # ADX filter: ranging market
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 25:
        return None, 0

    cur_close = closes[-1]
    cur_open = opens[-1]
    cur_high = highs[-1]
    cur_low = lows[-1]
    prev_close = closes[-2]
    prev_open = opens[-2]
    cur_body = cur_close - cur_open
    prev_body = prev_close - prev_open
    total_range = cur_high - cur_low

    if total_range <= 0:
        return None, 0

    upper_wick = (cur_high - max(cur_close, cur_open)) / total_range
    lower_wick = (min(cur_close, cur_open) - cur_low) / total_range

    # === PUT SIGNAL: long upper wick = sellers pushing back ===
    # conf=70: wick > 0.60 AND bearish body AND previous also bearish
    # conf=60: wick > 0.55 AND bearish body
    if upper_wick > 0.60 and cur_body < 0:
        if prev_body < 0:
            return "put", 70
        return "put", 60

    # === CALL SIGNAL DISABLED ===
    # Data shows CALL = 29% WR. Only trade PUT.
    return None, 0
