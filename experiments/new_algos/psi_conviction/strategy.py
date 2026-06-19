"""
PSI CONVICTION — Sequential Candle Momentum
=============================================
Detects BUILDING momentum via 3+ consecutive same-direction
candles where the TOTAL MOVE is meaningfully larger than
average recent movement.

Key insight: acceleration between INDIVIDUAL candles is too
noisy on 1-min. Instead, check if the STREAK total range
exceeds recent average by a meaningful margin.

+ Additional conditions on body size, trend structure, ADX.
"""
NAME = "psi_conviction"

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
    s_highs, s_lows = [], []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] > np.max(highs[i - lookback:i]) and \
           highs[i] > np.max(highs[i + 1:i + lookback + 1]):
            s_highs.append(highs[i])
        if lows[i] < np.min(lows[i - lookback:i]) and \
           lows[i] < np.min(lows[i + 1:i + lookback + 1]):
            s_lows.append(lows[i])
    return s_highs, s_lows


def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    if len(closes) < 25:
        return None, 0

    # ================================================================
    # 1. BASELINE METRICS
    # ================================================================
    bodies = closes - opens
    abs_bodies = np.abs(bodies)
    ranges = highs - lows

    avg_body = np.mean(abs_bodies[-15:-2])
    avg_range = np.mean(ranges[-15:-2])

    if avg_body <= 0 or avg_range <= 0:
        return None, 0

    # ================================================================
    # 2. SEQUENTIAL PATTERN DETECTION
    # Sequential pattern: count from end UNTIL direction changes
    first_dir = np.sign(bodies[-1])
    if first_dir == 0:
        return None, 0  # Flat last candle

    streak = 0
    for i in range(len(bodies) - 1, -1, -1):
        s = np.sign(bodies[i])
        if s == 0:
            break
        if s == first_dir:
            streak += 1
        else:
            break

    bull_streak = streak if first_dir > 0 else 0
    bear_streak = streak if first_dir < 0 else 0

    if bull_streak < 3 and bear_streak < 3:
        return None, 0

    is_bullish = bull_streak >= 3
    is_bearish = bear_streak >= 3
    streak_len = bull_streak if is_bullish else bear_streak

    # ================================================================
    # 3. STREAK STRENGTH — total range of the streak
    # ================================================================
    if is_bullish:
        streak_high = np.max(highs[-streak_len:])
        streak_low = np.min(lows[-streak_len:])
        streak_open = opens[-streak_len]
        streak_close = closes[-1]
        streak_bodies = abs_bodies[-streak_len:]
    else:
        streak_high = np.max(highs[-streak_len:])
        streak_low = np.min(lows[-streak_len:])
        streak_open = opens[-streak_len]
        streak_close = closes[-1]
        streak_bodies = abs_bodies[-streak_len:]

    streak_range = streak_high - streak_low
    net_move = abs(streak_close - streak_open)

    # Total range must exceed 1.2x average range (meaningful move)
    if streak_range < avg_range * 1.2:
        return None, 0

    # ================================================================
    # 4. LAST CANDLE CHECK — must not break the streak
    # ================================================================
    last_body = streak_bodies[-1]
    last_range = ranges[-1]

    # Last candle must be in the right direction (closing with the streak)
    if is_bullish and closes[-1] < opens[-1]:
        return None, 0  # Last candle is bearish = streak breaking
    if is_bearish and closes[-1] > opens[-1]:
        return None, 0  # Last candle is bullish = streak breaking

    # ================================================================
    # 5. RETRACEMENT CHECK — not too much against in the streak
    # ================================================================
    if is_bullish:
        # Any deep retrace during streak?
        highest = np.max(highs[-streak_len:])
        for j in range(streak_len):
            if closes[-streak_len + j] > opens[-streak_len + j]:
                continue
            # Bearish candle in bullish streak: check depth
            low_of_candle = lows[-streak_len + j]
            retrace_pct = (highest - low_of_candle) / highest * 100
            if retrace_pct > 0.6 and streak_len >= 4:
                return None, 0
    else:
        lowest = np.min(lows[-streak_len:])
        for j in range(streak_len):
            if closes[-streak_len + j] < opens[-streak_len + j]:
                continue
            high_of_candle = highs[-streak_len + j]
            retrace_pct = (high_of_candle - lowest) / lowest * 100 if lowest > 0 else 0
            if retrace_pct > 0.6 and streak_len >= 4:
                return None, 0

    # ================================================================
    # 6. TREND FILTER + ADX
    # ================================================================
    e8 = ema(closes, 8)
    e20 = ema(closes, 20)
    if e8 is None or e20 is None:
        return None, 0

    trender = e8[-1] > e20[-1]
    cur_adx = adx(highs, lows, closes, 14)

    # ================================================================
    # 7. CONFIDENCE SCORING
    # ================================================================
    if is_bullish:
        # Trend must support (either EMA aligned or price recovering)
        if not trender and closes[-1] < e20[-1]:
            return None, 0  # Strong trend conflict

        # Check RSI-2: only filter if EXTREME (> 97, avoids absolute top)
        if len(closes) >= 3:
            d = np.diff(closes)
            g = np.where(d > 0, d, 0)
            l = np.where(d < 0, -d, 0)
            ag = np.mean(g[:2])
            al = np.mean(l[:2])
            rsi2 = 100.0 - (100.0 / (1.0 + ag / al)) if al > 0 else 100.0
            if rsi2 > 97:
                return None, 0  # Absolute top chasing

        confidence = 55

        # Streak length bonus
        if streak_len >= 4:
            confidence += 10
        # Range bonus
        if streak_range > avg_range * 2.0:
            confidence += 10
        # ADX bonus
        if cur_adx and cur_adx > 20:
            confidence += 10
        # Last body bonus
        if last_body > avg_body * 1.5:
            confidence += 5

        if confidence < 60:
            return None, 0
        return "call", min(confidence, 90)

    if is_bearish:
        if trender and closes[-1] > e20[-1]:
            return None, 0

        # Check RSI-2: only filter if EXTREME (< 3, avoids absolute bottom)
        if len(closes) >= 3:
            d = np.diff(closes)
            g = np.where(d > 0, d, 0)
            l = np.where(d < 0, -d, 0)
            ag = np.mean(g[:2])
            al = np.mean(l[:2])
            rsi2 = 100.0 - (100.0 / (1.0 + ag / al)) if al > 0 else 100.0
            if rsi2 < 3:
                return None, 0  # Absolute bottom fishing

        confidence = 55
        if streak_len >= 4:
            confidence += 10
        if streak_range > avg_range * 2.0:
            confidence += 10
        if cur_adx and cur_adx > 20:
            confidence += 10
        if last_body > avg_body * 1.5:
            confidence += 5

        if confidence < 60:
            return None, 0
        return "put", min(confidence, 90)

    return None, 0
