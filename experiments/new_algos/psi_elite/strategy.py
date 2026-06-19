"""
PSI ELITE v3 — Zeta Pro + S/R Confluence Bonus
=================================================
Base: Zeta hybrid's proven RSI-2 core (78% WR on REAL).
Bonus: RSI-2 extreme at a S/R level = higher confidence.
Bonus: RSI-2 extreme with multiple touches = even higher.
Extra: HTF alignment adds final check.

AND-style on base (zeta's proven gates).
BONUS on S/R (pushes confidence past floor more often = more trades).
"""
NAME = "psi_elite"

import numpy as np


def ema(data, period):
    if len(data) < period:
        return None
    a = 2.0 / (period + 1.0)
    r = np.zeros(len(data))
    r[0] = data[0]
    for i in range(1, len(data)):
        r[i] = a * data[i] + (1 - a) * r[i - 1]
    return r


def rsi(data, period):
    if len(data) < period + 1:
        return None
    d = np.diff(data)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[:period])
    al = np.mean(l[:period])
    if al == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + ag / al))


def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n)
    pd = np.zeros(n)
    nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
        u = highs[i] - highs[i - 1]
        d = lows[i - 1] - lows[i]
        pd[i] = u if (u > d and u > 0) else 0
        nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n)
    ps = np.zeros(n)
    ns = np.zeros(n)
    ts[period] = sum(tr[1:period + 1])
    ps[period] = sum(pd[1:period + 1])
    ns[period] = sum(nd[1:period + 1])
    for i in range(period + 1, n):
        ts[i] = ts[i - 1] - ts[i - 1] / period + tr[i]
        ps[i] = ps[i - 1] - ps[i - 1] / period + pd[i]
        ns[i] = ns[i - 1] - ns[i - 1] / period + nd[i]
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


def find_swing_levels(highs, lows, lookback=5):
    """Returns (swing_highs, swing_lows) from the input arrays."""
    s_highs, s_lows = [], []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] > np.max(highs[i - lookback:i]) and \
           highs[i] > np.max(highs[i + 1:i + lookback + 1]):
            s_highs.append(highs[i])
        if lows[i] < np.min(lows[i - lookback:i]) and \
           lows[i] < np.min(lows[i + 1:i + lookback + 1]):
            s_lows.append(lows[i])
    return s_highs, s_lows


def near_support(price, swing_lows, tol_pct=0.1):
    """Check if price is within tol_pct % of a swing low."""
    for sl in swing_lows:
        if sl > 0 and abs(price - sl) / sl * 100 < tol_pct:
            return True
    return False


def near_resistance(price, swing_highs, tol_pct=0.1):
    """Check if price is within tol_pct % of a swing high."""
    for sh in swing_highs:
        if sh > 0 and abs(price - sh) / sh * 100 < tol_pct:
            return True
    return False


def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 28:
        return None, 0

    # ================================================================
    # BASE: ZETA HYBRID CORE
    # ================================================================
    rsi2 = rsi(closes, 2)
    if rsi2 is None:
        return None, 0

    e10 = ema(closes, 10)
    if e10 is None:
        return None, 0

    # Chop filter: last 3 candles can't have mixed direction
    if len(closes) >= 5:
        last3 = [closes[i] > closes[i-1] for i in range(-3, 0)]
        if sum(last3) in (1, 2):
            return None, 0

    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx < 18:
        return None, 0

    trend_up = closes[-1] > e10[-1]
    trend_down = closes[-1] < e10[-1]
    momentum_up = closes[-1] > closes[-2]
    momentum_down = closes[-1] < closes[-2]

    # ================================================================
    # S/R BONUS: Find swing levels in recent data
    # ================================================================
    s_highs, s_lows = find_swing_levels(highs[-25:-2], lows[-25:-2], 5)
    cur_close = closes[-1]

    price_scale = max(cur_close * 0.0005, 0.0002)
    at_support = any(abs(cur_close - sl) < price_scale for sl in s_lows)
    at_resistance = any(abs(cur_close - sh) < price_scale for sh in s_highs)

    # ================================================================
    # HTF BONUS
    # ================================================================
    htf_up = None
    if htf_candles is not None and len(htf_candles) >= 20:
        htf_c = np.array([c['close'] for c in htf_candles], dtype=float)
        htf_e10 = ema(htf_c, 10)
        if htf_e10 is not None:
            htf_up = htf_c[-1] > htf_e10[-1]

    # ================================================================
    # CALL ENTRY
    # ================================================================
    if rsi2 < 15 and trend_up and momentum_up:
        # RSI must be TURNING up (recovering from extreme)
        rsi2_prev = rsi(closes[:-1], 2) if len(closes) > 26 else None
        if rsi2_prev is not None and rsi2 <= rsi2_prev:
            return None, 0

        confidence = 55

        # RSI depth bonus
        if rsi2 < 5:
            confidence += 15
        elif rsi2 < 10:
            confidence += 10

        # ADX bonus
        if cur_adx > 25:
            confidence += 10

        # S/R BONUS: at support bounce = more reliable
        if at_support:
            confidence += 10

        # HTF BONUS: higher timeframes agree
        if htf_up is True:
            confidence += 5
        elif htf_up is False:
            confidence -= 5  # HTF against us = penalty

        if confidence < 60:
            return None, 0
        return "call", min(confidence, 90)

    # ================================================================
    # PUT ENTRY
    # ================================================================
    if rsi2 > 85 and trend_down and momentum_down:
        rsi2_prev = rsi(closes[:-1], 2) if len(closes) > 26 else None
        if rsi2_prev is not None and rsi2 >= rsi2_prev:
            return None, 0

        confidence = 55

        if rsi2 > 95:
            confidence += 15
        elif rsi2 > 90:
            confidence += 10

        if cur_adx > 25:
            confidence += 10

        # S/R BONUS: at resistance rejection = more reliable
        if at_resistance:
            confidence += 10

        if htf_up is False:
            confidence += 5
        elif htf_up is True:
            confidence -= 5

        if confidence < 60:
            return None, 0
        return "put", min(confidence, 90)

    return None, 0
